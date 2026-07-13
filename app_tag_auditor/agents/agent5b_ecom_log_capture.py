import re
import sys
import time
import threading
import subprocess
from datetime import datetime
import core.logger
from core.models import CapturedEcomLog

"""
EcomLogCaptureAgent — Firebase debug logcat capture for GA4 ecommerce events.

IMPORTANT: Firebase SDK versions differ in how nested items[] arrays are formatted
in debug logcat output. This agent targets the most commonly observed format:

  D/FA: Logging event (FE): add_to_cart(_o=app)
  D/FA:   Param:currency(_pv)=string=INR
  D/FA:   Param:value(_pv)=double=149900.0
  D/FA:   Bundle[{item_id(_pv)=string=SKU123, item_name(_pv)=string=Himalayan 450,
             price(_pv)=double=149900.0, quantity(_pv)=long=1}]

If live capture produces CapturedEcomLog entries with items=[] (empty items list),
run this command manually while triggering an ecom event in the app:
  adb logcat -s FA:D FA-SVC:D -v long
Inspect the raw output and adjust _parse_ecom_block's item regex accordingly.
"""

class EcomLogCaptureAgent:
    def __init__(self, device_serial: str | None = None):
        self.device_serial = device_serial
        self.logger = core.logger.get_logger(__name__)
        self._process = None
        self._reader_thread = None
        self._captured_buffer = []
        self._buffer_lock = threading.Lock()
        self._expected_names = set()

    def _adb_cmd(self, *args) -> list[str]:
        cmd = ["adb"]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        return cmd + list(args)

    def _parse_item_bundle(self, bundle_content: str) -> dict:
        items_dict = {}
        for piece in bundle_content.split(", "):
            piece = piece.strip()
            if not piece:
                continue
            match = re.search(r'^([\w]+)(?:\(_\w+\))?=\w+=(.+)$', piece)
            if match:
                k, v = match.group(1), match.group(2)
            else:
                parts = piece.split("=")
                if len(parts) >= 2:
                    k = parts[0]
                    v = parts[-1]
                else:
                    continue
            k = k.strip()
            v = v.strip()
            if k:
                items_dict[k] = v
        return items_dict

    def _parse_ecom_block(self, block_text: str) -> CapturedEcomLog | None:
        match = re.search(r'Logging event \(FE\): (\w+)\(', block_text)
        if not match:
            return None
        event_name = match.group(1)

        top_level_params = {}
        for k, v in re.findall(r'Param:(\w+)\(_pv\)=\w+=(.+)', block_text):
            k = k.strip()
            v = v.strip()
            if k and k != "items":
                top_level_params[k] = v

        items = []
        bundles = re.findall(r'Bundle\[\{(.*?)\}\]', block_text, re.DOTALL)
        if bundles:
            for b in bundles:
                item_dict = self._parse_item_bundle(b)
                if item_dict:
                    items.append(item_dict)
        else:
            alternates = re.findall(r'\{([^{}]+)\}', block_text)
            for alt in alternates:
                item_dict = self._parse_item_bundle(alt)
                if item_dict:
                    item_keys = {"item_id", "item_name", "price", "quantity"}
                    if any(ik in item_dict for ik in item_keys):
                        items.append(item_dict)

        return CapturedEcomLog(
            event_name=event_name,
            top_level_params=top_level_params,
            items=items,
            timestamp=datetime.now().isoformat(),
            source="logcat"
        )

    def _reader_loop(self, expected_names: set[str]) -> None:
        current_block = []
        try:
            for line in iter(self._process.stdout.readline, ""):
                if line.strip() == "":
                    if current_block:
                        block_text = "".join(current_block)
                        res = self._parse_ecom_block(block_text)
                        if res is not None:
                            if not expected_names or res.event_name in expected_names:
                                with self._buffer_lock:
                                    self._captured_buffer.append(res)
                        current_block = []
                else:
                    current_block.append(line)
            if current_block:
                block_text = "".join(current_block)
                res = self._parse_ecom_block(block_text)
                if res is not None:
                    if not expected_names or res.event_name in expected_names:
                        with self._buffer_lock:
                            self._captured_buffer.append(res)
        except Exception as e:
            self.logger.warning(f"Error in reader thread: {e}", exc_info=True)

    def start_capture(self, expected_event_names: set[str] | None = None) -> None:
        self._expected_names = expected_event_names or set()
        with self._buffer_lock:
            self._captured_buffer.clear()
        subprocess.run(self._adb_cmd("logcat", "-c"), capture_output=True)
        self._process = subprocess.Popen(
            self._adb_cmd("logcat", "-s", "FA:D", "FA-SVC:D", "-v", "long"),
            stdout=subprocess.PIPE, text=True, bufsize=1
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            args=(self._expected_names,),
            daemon=True
        )
        self._reader_thread.start()
        self.logger.info("[ECOM_LOG_CAPTURE_START] Logcat started for ecom events.")

    def stop_capture(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
            self._reader_thread = None
        self.logger.info("[ECOM_LOG_CAPTURE_STOP] Logcat capture stopped.")

    def get_captured_logs(self) -> list[CapturedEcomLog]:
        with self._buffer_lock:
            return list(self._captured_buffer)

    def capture_for_duration(self, duration_seconds: float,
                            expected_event_names: set[str]) -> list[CapturedEcomLog]:
        self.start_capture(expected_event_names)
        time.sleep(duration_seconds)
        self.stop_capture()
        return self.get_captured_logs()

if __name__ == "__main__":
    device_connected = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        lines = res.stdout.strip().split("\n")
        if len(lines) > 1:
            for line in lines[1:]:
                if line.strip().endswith("\tdevice"):
                    device_connected = True
                    break
    except Exception:
        pass

    agent = EcomLogCaptureAgent()

    print("=== SYNTHETIC PARSER TEST ===")
    SAMPLE_BLOCK = """\
    07-08 10:00:00.000  1234  5678 D FA     : Logging event (FE): add_to_cart(_o=app)
    07-08 10:00:00.001  1234  5678 D FA     :   Param:currency(_pv)=string=INR
    07-08 10:00:00.002  1234  5678 D FA     :   Param:value(_pv)=double=149900.0
    07-08 10:00:00.003  1234  5678 D FA     :   Bundle[{item_id(_pv)=string=SKU123, item_name(_pv)=string=Himalayan 450, price(_pv)=double=149900.0, quantity(_pv)=long=1, item_brand(_pv)=string=RoyalEnfield}]
    """

    result = agent._parse_ecom_block(SAMPLE_BLOCK)
    if result:
        print(result.model_dump_json(indent=2))

    c1 = result is not None
    c2 = result.event_name == "add_to_cart" if result else False
    c3 = result.top_level_params.get("currency") == "INR" if result else False
    c4 = result.top_level_params.get("value") == "149900.0" if result else False
    c5 = len(result.items) == 1 if result else False
    c6 = result.items[0].get("item_id") == "SKU123" if result else False
    c7 = result.items[0].get("item_brand") == "RoyalEnfield" if result else False

    if all([c1, c2, c3, c4, c5, c6, c7]):
        print("SAMPLE_BLOCK test: PASS")
    else:
        print("SAMPLE_BLOCK test: FAIL")

    bundle = 'item_id(_pv)=string=SKU999, item_name(_pv)=string=Super Meteor 650, price(_pv)=double=299900.0, quantity(_pv)=long=2'
    parsed = agent._parse_item_bundle(bundle)
    if parsed.get("item_id") == "SKU999" and parsed.get("quantity") == "2":
        print("bundle test: PASS")
    else:
        print("bundle test: FAIL")

    if device_connected:
        print("=== LIVE ADB CAPTURE MODE (15 seconds) ===")
        print("Interact with ecommerce features in the app now...")
        ecom_names = {"add_to_cart", "view_item", "purchase", "view_item_list",
                      "begin_checkout", "view_cart", "select_item"}
        results = agent.capture_for_duration(15, ecom_names)
        print(f"Captured {len(results)} ecom log(s).")
        for r in results:
            print(r.model_dump_json(indent=2))
        if not results:
            print("No ecom events captured. If this is unexpected, run `adb logcat -s FA:D FA-SVC:D -v long` manually and check the format — adjust _parse_ecom_block regex if needed.")
    else:
        print("=== NO DEVICE DETECTED — skipping live capture ===")
        print("Connect a device and run again to test live capture.")
