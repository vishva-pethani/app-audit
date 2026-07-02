import os
import sys
import re
import pathlib
from core.logger import get_logger
from core.models import ExpectedEvent, CodeLocation

logger = get_logger(__name__)

class CodebaseMapperAgent:
    """
    Agent2 CodebaseMapperAgent:
    Scans the decompiled app source files to locate where the expected analytics
    events are triggered, extracting class names, method names, and confidence scores.
    """
    def __init__(self, decompiled_source_dir: str):
        self.decompiled_source_dir = decompiled_source_dir

    def _iter_java_files(self):
        """Yields pathlib.Path objects for every Java file under the source directory."""
        return pathlib.Path(self.decompiled_source_dir).rglob("*.java")

    def _find_enclosing_class(self, lines: list[str], match_idx: int) -> str:
        """Scans backwards from match_idx to find the enclosing class declaration."""
        class_regex = re.compile(r'class\s+(\w+)')
        for idx in range(match_idx, -1, -1):
            match = class_regex.search(lines[idx])
            if match:
                return match.group(1)
        return "UnknownClass"

    def _find_enclosing_method(self, lines: list[str], match_idx: int) -> str:
        """Scans backwards from match_idx to find the enclosing method signature."""
        method_regex = re.compile(
            r'(?:public|private|protected)\s+[\w<>\[\],\s]+\s+(\w+)\s*\([^)]*\)\s*\{?'
        )
        for idx in range(match_idx, -1, -1):
            match = method_regex.search(lines[idx])
            if match:
                return match.group(1)
        return "unknown_method"

    def map_event(self, event: ExpectedEvent) -> CodeLocation:
        """
        Locates the event inside Java source files and scores confidence.
        """
        best_file = None
        best_line_idx = -1
        best_matched_params_count = -1
        best_lines = []
        target_literal = f'"{event.event_name}"'

        # 1. Look for the exact event_name literal inside quotes
        for path in self._iter_java_files():
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                if target_literal in line:
                    # Check parameter occurrences within a +/- 15 line window
                    start_idx = max(0, idx - 15)
                    end_idx = min(len(lines) - 1, idx + 15)
                    window_content = "\n".join(lines[start_idx:end_idx + 1])

                    matched_count = sum(
                        1 for param in event.expected_params
                        if f'"{param.param_name}"' in window_content
                    )

                    if matched_count > best_matched_params_count:
                        best_matched_params_count = matched_count
                        best_file = path
                        best_line_idx = idx
                        best_lines = lines
                    break  # Stop checking further in this file

        if best_file is not None:
            total_params = len(event.expected_params)
            if total_params == 0:
                confidence = 1.0
            elif best_matched_params_count == total_params:
                confidence = 1.0
            else:
                confidence = 0.5 + 0.5 * (best_matched_params_count / total_params)

            enclosing_class = self._find_enclosing_class(best_lines, best_line_idx)
            enclosing_method = self._find_enclosing_method(best_lines, best_line_idx)

            return CodeLocation(
                event_name=event.event_name,
                file_path=str(best_file),
                line_number=best_line_idx + 1,
                matched_snippet=best_lines[best_line_idx].strip(),
                breadcrumb=[enclosing_class, enclosing_method],
                confidence=confidence
            )

        # 2. Fallback: Search for any string in event.keywords appearing in any file
        for path in self._iter_java_files():
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                for kw in event.keywords:
                    if kw in line.lower():
                        enclosing_class = self._find_enclosing_class(lines, idx)
                        enclosing_method = self._find_enclosing_method(lines, idx)
                        return CodeLocation(
                            event_name=event.event_name,
                            file_path=str(path),
                            line_number=idx + 1,
                            matched_snippet=line.strip(),
                            breadcrumb=[enclosing_class, enclosing_method],
                            confidence=0.3
                        )

        # 3. No match found
        return CodeLocation(
            event_name=event.event_name,
            file_path="",
            line_number=0,
            matched_snippet="",
            breadcrumb=[],
            confidence=0.0
        )

    def run(self, expected_events: list[ExpectedEvent]) -> list[CodeLocation]:
        """Maps all expected events to their locations in the source files in a single pass."""
        event_by_name = {e.event_name: e for e in expected_events}
        event_names = list(event_by_name.keys())
        
        from collections import defaultdict
        kw_to_events = defaultdict(list)
        for e in expected_events:
            for kw in e.keywords:
                kw_to_events[kw.lower()].append(e)
                
        # Pre-compile regex patterns for fast matching
        import re
        pattern = None
        if event_names:
            pattern = re.compile(r'"(' + '|'.join(re.escape(name) for name in event_names) + r')"')
            
        kw_pattern = None
        if kw_to_events:
            kw_pattern = re.compile(r'\b(' + '|'.join(re.escape(kw) for kw in kw_to_events.keys()) + r')\b', re.IGNORECASE)
            
        best_matches = {} # event_name -> (path, line_idx, matched_count, lines)
        fallback_matches = {} # event_name -> (path, line_idx, snippet, breadcrumb)
        
        for path in self._iter_java_files():
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue
                
            matched_events = set()
            if pattern:
                matched_events = set(pattern.findall(content))
                
            matched_kws = set()
            if kw_pattern:
                matched_kws = {kw.lower() for kw in kw_pattern.findall(content)}
                
            if not matched_events and not matched_kws:
                continue
                
            lines = content.splitlines()
            
            # 1. Process exact matches
            if matched_events:
                for idx, line in enumerate(lines):
                    for name in matched_events:
                        target_literal = f'"{name}"'
                        if target_literal in line:
                            event = event_by_name[name]
                            start_idx = max(0, idx - 15)
                            end_idx = min(len(lines) - 1, idx + 15)
                            window_content = "\n".join(lines[start_idx:end_idx + 1])
                            
                            matched_count = sum(
                                1 for param in event.expected_params
                                if f'"{param.param_name}"' in window_content
                            )
                            
                            current_best = best_matches.get(name)
                            if current_best is None or matched_count > current_best[2]:
                                best_matches[name] = (path, idx, matched_count, lines)
                                
            # 2. Process fallback matches
            if matched_kws:
                for idx, line in enumerate(lines):
                    line_lower = line.lower()
                    for kw in matched_kws:
                        if kw in line_lower:
                            for event in kw_to_events[kw]:
                                if event.event_name not in best_matches and event.event_name not in fallback_matches:
                                    enclosing_class = self._find_enclosing_class(lines, idx)
                                    enclosing_method = self._find_enclosing_method(lines, idx)
                                    fallback_matches[event.event_name] = (path, idx, line.strip(), [enclosing_class, enclosing_method])
                                    
        # Build final CodeLocation results list
        results = []
        for event in expected_events:
            name = event.event_name
            if name in best_matches:
                path, idx, matched_count, lines = best_matches[name]
                total_params = len(event.expected_params)
                if total_params == 0:
                    confidence = 1.0
                elif matched_count == total_params:
                    confidence = 1.0
                else:
                    confidence = 0.5 + 0.5 * (matched_count / total_params)
                    
                enclosing_class = self._find_enclosing_class(lines, idx)
                enclosing_method = self._find_enclosing_method(lines, idx)
                
                results.append(CodeLocation(
                    event_name=name,
                    file_path=str(path),
                    line_number=idx + 1,
                    matched_snippet=lines[idx].strip(),
                    breadcrumb=[enclosing_class, enclosing_method],
                    confidence=confidence
                ))
            elif name in fallback_matches:
                path, idx, snippet, breadcrumb = fallback_matches[name]
                results.append(CodeLocation(
                    event_name=name,
                    file_path=str(path),
                    line_number=idx + 1,
                    matched_snippet=snippet,
                    breadcrumb=breadcrumb,
                    confidence=0.3
                ))
            else:
                logger.warning(f"Could not map event '{name}' in codebase (confidence 0.0).")
                results.append(CodeLocation(
                    event_name=name,
                    file_path="",
                    line_number=0,
                    matched_snippet="",
                    breadcrumb=[],
                    confidence=0.0
                ))
                
        return results

if __name__ == "__main__":
    import tempfile
    import shutil
    from agents.agent1_schema_reader import SchemaReaderAgent

    temp_dir = None
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.endswith(".apk"):
            print(f"Decompiling {arg} for codebase mapping...")
            from core.apk_decompiler import ApkDecompiler
            source_dir = ApkDecompiler().decompile(arg)
        else:
            source_dir = arg
    else:
        print("No path given — using built-in synthetic fixture for self-test.")
        temp_dir = tempfile.mkdtemp()
        fixture_content = """package com.royalenfield.app.fragments;

public class MyREFragment extends Fragment {

    private void logScreenView() {
        Bundle bundle = new Bundle();
        bundle.putString("screenname", "My_RE_screen");
        firebaseAnalytics.logEvent("screen_view", bundle);
    }

    private void onAddMotorcycleClicked() {
        Bundle bundle = new Bundle();
        bundle.putString("screenname", "My_RE_screen");
        firebaseAnalytics.logEvent("add_motorcycle", bundle);
    }

    private void onBookNowClicked(String modelName) {
        Bundle bundle = new Bundle();
        bundle.putString("clickText", "Book Now");
        bundle.putString("modelName", modelName);
        bundle.putString("sectionHeading", "Service Booking");
        bundle.putString("screenname", "My_RE_screen");
        firebaseAnalytics.logEvent("book_service", bundle);
    }

    private void onServiceHistoryClicked(String modelName) {
        Bundle bundle = new Bundle();
        bundle.putString("clickText", "My Service History");
        bundle.putString("modelName", modelName);
        bundle.putString("screenname", "My_RE_screen");
        firebaseAnalytics.logEvent("view_service_history", bundle);
    }
}
"""
        fixture_path = os.path.join(temp_dir, "MyREFragment.java")
        with open(fixture_path, "w", encoding="utf-8") as f:
            f.write(fixture_content)
        source_dir = temp_dir

    schema_reader = SchemaReaderAgent()
    expected_events = schema_reader.run()

    mapper = CodebaseMapperAgent(source_dir)
    locations = mapper.run(expected_events)

    print("\nMapping Results:\n")
    for loc in locations:
        print(loc.model_dump_json(indent=2))
        print("-" * 40)

    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
