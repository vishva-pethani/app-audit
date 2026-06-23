import os
import json
import xml.etree.ElementTree as ET
from typing import Optional, Tuple
from core.logger import get_logger
import core.ui_hierarchy

logger = get_logger(__name__)

class ScreenDetector:
    def __init__(
        self,
        activity_map_path: str = "schemas/screen_activity_map.json",
        signature_map_path: str = "schemas/screen_signatures.json",
        activity_map: Optional[dict] = None,
        signature_map: Optional[dict] = None
    ):
        if activity_map is not None:
            self.activity_map = activity_map
        else:
            self.activity_map = self._load_json_safe(activity_map_path)

        if signature_map is not None:
            self.signature_map = signature_map
        else:
            self.signature_map = self._load_json_safe(signature_map_path)

    def _load_json_safe(self, path: str) -> dict:
        if not os.path.exists(path):
            logger.warning(f"Map file {path} missing, using empty dict.")
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading {path}: {e}, using empty dict.")
            return {}

    def detect(self, driver) -> Tuple[Optional[str], str]:
        # 1. Try SIGNATURE path first
        xml_str = core.ui_hierarchy.dump_hierarchy(driver)
        root = core.ui_hierarchy.parse_hierarchy(xml_str)
        if root is not None:
            matches = []
            for screen_name, substring in self.signature_map.items():
                sub_lower = substring.lower()
                matched = False
                for node in root.iter():
                    text = node.attrib.get('text') or ''
                    desc = node.attrib.get('content-desc') or ''
                    res_id = node.attrib.get('resource-id') or ''
                    haystack = f"{text} {desc} {res_id}".lower()
                    if sub_lower in haystack:
                        matched = True
                        break
                if matched:
                    matches.append(screen_name)

            if len(matches) > 1:
                logger.warning(
                    f"Ambiguity in screen detection: multiple screens matched signatures {matches}. "
                    f"Using the first match: {matches[0]}"
                )
            if matches:
                return matches[0], "signature"

        # 2. Fall back to ACTIVITY
        try:
            current_act = driver.current_activity
        except Exception as e:
            logger.warning(f"Failed to fetch current_activity from driver: {e}")
            return None, "unknown"

        if current_act:
            for act_substring, screen_name in self.activity_map.items():
                if act_substring.lower() in current_act.lower():
                    return screen_name, "activity"

        return None, "unknown"

class FakeDriver:
    def __init__(self):
        self.page_source = '<?xml version="1.0" encoding="utf-8"?><node text="My RE" content-desc="" resource-id="" />'
        self.current_activity = ".SomeOtherActivity"

if __name__ == "__main__":
    driver = FakeDriver()
    passed = 0
    total = 3

    # Case A
    detector_a = ScreenDetector(signature_map={"My_RE_screen": "My RE"}, activity_map={})
    res_a, src_a = detector_a.detect(driver)
    if res_a == "My_RE_screen" and src_a == "signature":
        print("Case A: PASS")
        passed += 1
    else:
        print(f"Case A: FAIL (got {res_a}, {src_a})")

    # Case B
    detector_b = ScreenDetector(signature_map={}, activity_map={"SomeOtherActivity": "Fallback_screen"})
    res_b, src_b = detector_b.detect(driver)
    if res_b == "Fallback_screen" and src_b == "activity":
        print("Case B: PASS")
        passed += 1
    else:
        print(f"Case B: FAIL (got {res_b}, {src_b})")

    # Case C
    detector_c = ScreenDetector(signature_map={}, activity_map={})
    res_c, src_c = detector_c.detect(driver)
    if res_c is None and src_c == "unknown":
        print("Case C: PASS")
        passed += 1
    else:
        print(f"Case C: FAIL (got {res_c}, {src_c})")

    print(f"Summary: {passed}/{total} test cases passed.")
