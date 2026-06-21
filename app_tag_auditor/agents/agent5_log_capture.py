"""
Agent5 LogCaptureAgent:
Tails and parses adb logcat output for Firebase Analytics debug events.
"""
import os
import re
import sys
import time
import queue
import threading
import subprocess
from datetime import datetime
from core.logger import get_logger
from core.models import CapturedLog

logger = get_logger(__name__)

class LogCaptureAgent:
    """Captures Firebase Analytics debug event logs via `adb logcat`."""
    def __init__(self, device_serial: str | None = None):
        self.device_serial = device_serial
        self.process, self._queue, self._thread = None, None, None

    def _adb_cmd(self, *args) -> list[str]:
        cmd = ["adb"]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        return cmd + list(args)

    def _parse_line(self, line: str) -> CapturedLog | None:
        line_str = line.strip()
        logger.info(f"[LOG_PARSE_TRY] Parsing log line: {line_str}")
        
        # Format 1: Legacy/Developer logging format - Logging event (FE): event_name(params)
        match1 = re.search(r'Logging event \(FE\): (\w+)\((.*)\)$', line_str)
        if match1:
            event_name, params_raw = match1.group(1), match1.group(2)
            raw_params = {}
            if params_raw:
                for piece in params_raw.split(", "):
                    if "=" in piece:
                        k, v = piece.split("=", 1)
                        clean_k = re.sub(r'\(_\w+\)$', '', k.strip())
                        if not clean_k.startswith("_"):
                            raw_params[clean_k] = v.strip()
            log = CapturedLog(
                event_name=event_name, raw_params=raw_params,
                timestamp=datetime.now().isoformat(), source="logcat"
            )
            logger.info(f"[LOG_PARSE_SUCCESS] Matched Format 1: {log}")
            return log
            
        # Format 2: Real verbose device logging format - Logging event: origin=app,name=event_name(_vs),params=Bundle[[params]] or Bundle[{params}]
        match2 = re.search(r'Logging event:\s*origin=\w+,\s*name=([\w_]+)(?:\(_\w+\))?,\s*params=Bundle\[(?:\[|\{)(.*?)(?:\]|\})\]', line_str)
        if match2:
            event_name, params_raw = match2.group(1), match2.group(2)
            raw_params = {}
            if params_raw:
                for piece in params_raw.split(","):
                    if "=" in piece:
                        k, v = piece.split("=", 1)
                        clean_k = re.sub(r'\(_\w+\)$', '', k.strip())
                        clean_v = v.strip().rstrip("]").rstrip("}").strip()
                        if not clean_k.startswith("_"):
                            raw_params[clean_k] = clean_v
            log = CapturedLog(
                event_name=event_name, raw_params=raw_params,
                timestamp=datetime.now().isoformat(), source="logcat"
            )
            logger.info(f"[LOG_PARSE_SUCCESS] Matched Format 2: {log}")
            return log
            
        return None

    def parse_lines(self, lines: list[str]) -> list[CapturedLog]:
        """Parses a list of logcat lines, resolving both single-line and multi-line formats."""
        events = []
        i = 0
        while i < len(lines):
            line = lines[i]
            line_strip = line.strip()
            
            # Format 3: Multi-line Block Format
            if "event {" in line_strip and "FA-SVC" in line:
                raw_lines = [line.rstrip()]
                event_lines = []
                depth = 1
                i += 1
                while i < len(lines) and depth > 0:
                    curr_line = lines[i]
                    raw_lines.append(curr_line.rstrip())
                    
                    # Clean out logcat prefix
                    prefix_match = re.search(r'FA(?:-SVC)?\s*(?:\(\s*\d+\s*\))?\s*:\s*(.*)', curr_line)
                    content = prefix_match.group(1) if prefix_match else curr_line.strip()
                    
                    if "{" in content:
                        depth += content.count("{")
                    if "}" in content:
                        depth -= content.count("}")
                    event_lines.append(content)
                    if depth <= 0:
                        break
                    i += 1
                
                event_name = "unknown_event"
                params = {}
                in_param = False
                current_param_name = None
                current_param_val = None
                for ev_line in event_lines:
                    ev_line_strip = ev_line.strip()
                    if ev_line_strip.startswith("param {"):
                        in_param = True
                    elif ev_line_strip.startswith("}"):
                        if in_param and current_param_name:
                            clean_k = re.sub(r'\(_\w+\)$', '', current_param_name.strip())
                            if not clean_k.startswith("_"):
                                params[clean_k] = current_param_val
                        in_param = False
                        current_param_name = None
                        current_param_val = None
                    elif in_param:
                        if ev_line_strip.startswith("name:"):
                            current_param_name = ev_line_strip.split(":", 1)[1].replace('"', '').strip()
                        elif "value:" in ev_line_strip or "string_value:" in ev_line_strip or "int_value:" in ev_line_strip:
                            current_param_val = ev_line_strip.split(":", 1)[1].replace('"', '').strip()
                    else:
                        if ev_line_strip.startswith("name:"):
                            raw_event_name = ev_line_strip.split(":", 1)[1].replace('"', '').strip()
                            event_name = re.sub(r'\(_\w+\)$', '', raw_event_name)
                
                log = CapturedLog(
                    event_name=event_name,
                    raw_params=params,
                    timestamp=datetime.now().isoformat(),
                    source="logcat"
                )
                logger.info(f"[LOG_PARSE_SUCCESS] Matched Multi-line Block Format: {log}")
                events.append(log)
            else:
                # Fall back to single-line parsing
                parsed = self._parse_line(line)
                if parsed:
                    events.append(parsed)
            i += 1
        return events

    def start_capture(self) -> None:
        logger.info("[LOG_CAPTURE_START] Clearing logcat and starting background process...")
        subprocess.run(self._adb_cmd("logcat", "-c"), capture_output=True)
        self.process = subprocess.Popen(
            self._adb_cmd("logcat", "-s", "FA:V", "FA-SVC:V"),
            stdout=subprocess.PIPE, text=True, bufsize=1, errors='replace'
        )
        self._queue = queue.Queue()
        def reader():
            try:
                for line in iter(self.process.stdout.readline, ''):
                    safe_line = line.strip().encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                    logger.info(f"[LOG_CAPTURE_RAW] {safe_line}")
                    self._queue.put(line)
            except Exception:
                logger.warning("Error in reader thread:", exc_info=True)
        self._thread = threading.Thread(target=reader, daemon=True)
        self._thread.start()

    def stop_capture(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def capture_for_duration(self, duration: float, expected_names: set[str]) -> list[CapturedLog]:
        self.start_capture()
        raw_lines = []
        start = time.time()
        try:
            while time.time() - start < duration:
                try:
                    remaining = duration - (time.time() - start)
                    if remaining <= 0:
                        break
                    line = self._queue.get(timeout=min(0.5, remaining))
                    raw_lines.append(line)
                except queue.Empty:
                    continue
        finally:
            self.stop_capture()

        # Drain any remaining lines from the queue
        while not self._queue.empty():
            try:
                raw_lines.append(self._queue.get_nowait())
            except queue.Empty:
                break

        parsed = self.parse_lines(raw_lines)
        return [log for log in parsed if log.event_name in expected_names]

    def write_logs_to_output(self, logs: list[CapturedLog], writer, tab: str = "RawLogs") -> None:
        import json
        writer.ensure_headers(tab, ["event_name", "raw_params", "timestamp", "source"])
        for l in logs:
            writer.append_row(tab, {
                "event_name": l.event_name, "raw_params": json.dumps(l.raw_params),
                "timestamp": l.timestamp, "source": l.source
            })

    def run(self, duration: float, expected_names: set[str], writer) -> list[CapturedLog]:
        """Runs log capture agent logic."""
        logs = self.capture_for_duration(duration, expected_names)
        self.write_logs_to_output(logs, writer)
        return logs

if __name__ == "__main__":
    from core.config import get_settings
    from core.output_writer import LocalExcelWriter
    
    settings = get_settings()
    device_connected = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
        device_connected = any(line.strip().endswith("\tdevice") for line in res.stdout.strip().split("\n")[1:])
    except Exception:
        pass

    force_synthetic = "--synthetic" in sys.argv
    if device_connected and not force_synthetic:
        print("=== LIVE ADB CAPTURE MODE ===")
        from agents.agent1_schema_reader import SchemaReaderAgent
        events = SchemaReaderAgent().run()
        expected_names = {e.event_name for e in events}
        agent = LogCaptureAgent()
        if settings.ANDROID_APP_PACKAGE:
            subprocess.run(agent._adb_cmd("shell", "setprop", "debug.firebase.analytics.app", settings.ANDROID_APP_PACKAGE), capture_output=True)
            print(f"Debug mode enabled for: {settings.ANDROID_APP_PACKAGE}")
        print("Please interact with the app now...")
        captured = agent.capture_for_duration(15.0, expected_names)
        LocalExcelWriter().ensure_headers("RawLogs", ["event_name", "raw_params", "timestamp", "source"])
        agent.write_logs_to_output(captured, LocalExcelWriter())
        print(f"Captured {len(captured)} logs. Written to Excel.")
    else:
        print("=== SYNTHETIC SELF-TEST MODE ===")
        sample_lines = [
            "D/FA: Logging event (FE): screen_view(_o=app, screenname(_pn)=My_RE_screen)",
            "D/FA: Logging event (FE): add_motorcycle(_o=app, screenname(_pn)=My_RE_screen)",
            "D/FA-SVC  : Logging event: origin=app,name=book_service,params=Bundle[[clickText=Book Now, modelName=Super Meteor 650, sectionHeading=Service Booking, screenname=My_RE_screen, ga_event_origin(_o)=app, manual_tracking(_mst)=1 ]]",
            "D/FA-SVC  : Logging event: origin=app,name=view_service_history(_vs),params=Bundle[[clickText=My Service History, modelName=Himalayan 450, screenname=My_RE_screen ]]",
            "V/FA-SVC  ( 1234): event {",
            "V/FA-SVC  ( 1234):   name: view_search_results",
            "V/FA-SVC  ( 1234):   param {",
            "V/FA-SVC  ( 1234):     name: search_term",
            "V/FA-SVC  ( 1234):     string_value: cruiser",
            "V/FA-SVC  ( 1234):   }",
            "V/FA-SVC  ( 1234): }"
        ]
        agent = LogCaptureAgent()
        parsed = agent.parse_lines(sample_lines)
        for log in parsed:
            print(log.model_dump_json(indent=2))
        
        os.makedirs("./tmp", exist_ok=True)
        temp_writer = LocalExcelWriter("./tmp/test_logs.xlsx")
        agent.write_logs_to_output(parsed, temp_writer)
        print("Read back logs:")
        for row in temp_writer.read_all("RawLogs"):
            print(row)
        if os.path.exists("./tmp/test_logs.xlsx"):
            os.remove("./tmp/test_logs.xlsx")
