"""
Firebase debug-mode logcat formatting for nested 'items' arrays varies meaningfully across SDK versions. The regex below targets the most commonly documented format. If live capture yields zero items, run `adb logcat -s FA:D FA-SVC:D -v long` manually during a real ecommerce action (add_to_cart, purchase, etc.), inspect the raw multi-line block format, and adjust _parse_ecom_block accordingly.
"""

import os
import sys
import re
import subprocess
from datetime import datetime

# Add the project root to sys.path to allow execution from any directory
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.logger import get_logger
from core.models import CapturedEcomLog

logger = get_logger(__name__)

class EcomLogCaptureAgent:
    def __init__(self, device_serial: str | None = None):
        self.device_serial = device_serial

    def _adb_cmd(self, *args) -> list[str]:
        cmd = ["adb"]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        return cmd + list(args)

    def _parse_ecom_block(self, block_text: str) -> CapturedEcomLog | None:
        match = re.search(r'Logging event \(FE\): (\w+)\(', block_text)
        if not match:
            return None
        event_name = match.group(1)

        top_level_params = {}
        params_matches = re.findall(r'Param:(\w+)\(_pv\)=\w+=(.+)', block_text)
        for k, v in params_matches:
            if k != "items":
                top_level_params[k.strip()] = v.strip()

        items = []
        bundle_matches = re.findall(r'Bundle\[\{(.*?)\}\]', block_text, re.DOTALL)
        for bundle_str in bundle_matches:
            item_dict = {}
            pieces = [p.strip() for p in re.split(r',', bundle_str)]
            for piece in pieces:
                if not piece:
                    continue
                if "=" in piece:
                    parts = piece.rsplit("=", 1)
                    key_part = parts[0].strip()
                    val = parts[1].strip()
                    
                    if "(" in key_part:
                        key = key_part.split("(", 1)[0].strip()
                    else:
                        key = key_part
                    
                    key = re.sub(r'\(_\w+\)$', '', key).strip()
                    item_dict[key] = val
            items.append(item_dict)

        return CapturedEcomLog(
            event_name=event_name,
            top_level_params=top_level_params,
            items=items,
            timestamp=datetime.now().isoformat(),
            source="logcat"
        )

    def capture_for_duration(self, duration_seconds: float, expected_event_names: set[str]) -> list[CapturedEcomLog]:
        subprocess.run(self._adb_cmd("logcat", "-c"), capture_output=True)
        
        stdout = ""
        try:
            res = subprocess.run(
                self._adb_cmd("logcat", "-s", "FA:D", "FA-SVC:D", "-v", "long"),
                timeout=duration_seconds,
                capture_output=True,
                text=True
            )
            stdout = res.stdout
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout or ""

        blocks = re.split(r'\n\s*\n', stdout)
        logs = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            log = self._parse_ecom_block(block)
            if log and log.event_name in expected_event_names:
                logs.append(log)
        return logs

if __name__ == "__main__":
    device_connected = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
        device_connected = any(line.strip().endswith("\tdevice") for line in res.stdout.strip().split("\n")[1:])
    except Exception:
        pass

    agent = EcomLogCaptureAgent()
    if device_connected:
        print("=== LIVE ADB CAPTURE MODE ===")
        print("Please interact with the app now (add_to_cart, purchase, view_item, view_item_list)...")
        results = agent.capture_for_duration(15.0, {"add_to_cart", "purchase", "view_item", "view_item_list"})
        for log in results:
            print(log.model_dump_json(indent=2))
            print("-" * 40)
    else:
        print("=== SYNTHETIC FIXTURE MODE ===")
        SAMPLE_BLOCK = (
            "Logging event (FE): add_to_cart(_o=app)\n"
            "Param:currency(_pv)=string=INR\n"
            "Param:value(_pv)=double=149900.0\n"
            "Param:items(_pv)=bundle[]=[Bundle[{item_id(_pv)=string=SKU123, "
            "item_name(_pv)=string=Himalayan 450, price(_pv)=double=149900.0, "
            "quantity(_pv)=long=1}]]"
        )
        parsed = agent._parse_ecom_block(SAMPLE_BLOCK)
        if parsed:
            print(parsed.model_dump_json(indent=2))
        else:
            print("Failed to parse sample block.")
