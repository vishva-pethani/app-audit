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
        match = re.search(r'Logging event \(FE\): (\w+)\((.*)\)$', line.strip())
        if not match:
            return None
        event_name, params_raw = match.group(1), match.group(2)
        raw_params = {}
        if params_raw:
            for piece in params_raw.split(", "):
                if "=" in piece:
                    k, v = piece.split("=", 1)
                    clean_k = re.sub(r'\(_\w+\)$', '', k.strip())
                    if not clean_k.startswith("_"):
                        raw_params[clean_k] = v.strip()
        return CapturedLog(
            event_name=event_name, raw_params=raw_params,
            timestamp=datetime.now().isoformat(), source="logcat"
        )

    def start_capture(self) -> None:
        subprocess.run(self._adb_cmd("logcat", "-c"), capture_output=True)
        self.process = subprocess.Popen(
            self._adb_cmd("logcat", "-s", "FA:D", "FA-SVC:D"),
            stdout=subprocess.PIPE, text=True, bufsize=1
        )
        self._queue = queue.Queue()
        def reader():
            try:
                for line in iter(self.process.stdout.readline, ''):
                    self._queue.put(line)
            except Exception:
                pass
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
        results, start = [], time.time()
        try:
            while time.time() - start < duration:
                try:
                    remaining = duration - (time.time() - start)
                    if remaining <= 0:
                        break
                    line = self._queue.get(timeout=min(0.5, remaining))
                    log = self._parse_line(line)
                    if log and log.event_name in expected_names:
                        results.append(log)
                except queue.Empty:
                    continue
        finally:
            self.stop_capture()
        return results

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

    if device_connected:
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
            "D/FA: Logging event (FE): book_service(_o=app, clickText(_pn)=Book Now, modelName(_pn)=Super Meteor 650, sectionHeading(_pn)=Service Booking, screenname(_pn)=My_RE_screen)",
            "D/FA: Logging event (FE): view_service_history(_o=app, clickText(_pn)=My Service History, modelName(_pn)=Himalayan 450, screenname(_pn)=My_RE_screen)"
        ]
        agent = LogCaptureAgent()
        parsed = [agent._parse_line(line) for line in sample_lines if agent._parse_line(line)]
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
