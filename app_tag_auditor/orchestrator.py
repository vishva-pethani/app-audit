import os, re, sys, time, inspect, subprocess
from datetime import datetime
from typing import Any, Tuple, Optional
from core.logger import get_logger
from core.config import get_settings
from core.output_writer import LocalExcelWriter
from core.apk_decompiler import ApkDecompiler
from core.models import ExpectedEvent, CrawlPlan, EventRuntimeCapture, CapturedLog
from core.screen_detector import ScreenDetector
from agents.agent1_schema_reader import SchemaReaderAgent
from agents.agent2_codebase_mapper import CodebaseMapperAgent
from agents.agent3_crawl_planner import CrawlPlannerAgent
from agents.agent4_crawl_executor import CrawlExecutorAgent
from agents.agent5_log_capture import LogCaptureAgent
from agents.agent6_telemetry_validator import TelemetryValidatorAgent
from agents.agent7_runtime_validator import RuntimeValidatorAgent
from agents.agent8_validation_combiner import ValidationCombinerAgent

logger = get_logger(__name__)

class RuntimeAuditOrchestrator:
    def __init__(self, crawl_executor, log_agent, screen_detector: ScreenDetector, all_events: list[ExpectedEvent]):
        self.crawl_executor, self.log_agent, self.screen_detector, self.all_events = crawl_executor, log_agent, screen_detector, all_events

    def run_single_event(self, event: ExpectedEvent, plan: CrawlPlan) -> EventRuntimeCapture:
        logger.info(f"Running scenario for event: {event.event_name}")
        self.log_agent.start_capture({e.event_name for e in self.all_events})
        sig = inspect.signature(self.crawl_executor.execute_plan)
        if 'event' in sig.parameters: self.crawl_executor.execute_plan(plan, event=event)
        else: self.crawl_executor.execute_plan(plan)
        trigger_timestamp = datetime.now().isoformat()
        time.sleep(get_settings().RUNTIME_CAPTURE_BUFFER_SECONDS)
        driver = self.crawl_executor.driver
        det, src = self.screen_detector.detect(driver) if driver else (None, "unknown")
        self.log_agent.stop_capture()
        return EventRuntimeCapture(
            event_name=event.event_name, trigger_timestamp=trigger_timestamp,
            captured_logs=self.log_agent.get_captured_logs(), detected_screen_after=det, detection_source=src
        )

    def reset_best_effort(self) -> None:
        """Best-effort reset; may not reliably return to start."""
        logger.info("Executing best-effort reset...")
        driver = self.crawl_executor.driver
        if not driver: return
        for i in range(3):
            try:
                driver.back()
                time.sleep(1.0)
            except Exception as e:
                logger.warning(f"Failed to press back on attempt {i+1}: {e}")
                break

    def run_full_audit(self, events_and_plans: list[tuple[ExpectedEvent, CrawlPlan]]) -> list[EventRuntimeCapture]:
        captures = []
        for idx, (event, plan) in enumerate(events_and_plans):
            logger.info(f"Auditing event {idx+1}/{len(events_and_plans)}: {event.event_name}")
            captures.append(self.run_single_event(event, plan))
            if idx < len(events_and_plans) - 1: self.reset_best_effort()
        return captures

def run_pipeline(apk_path: str, sheet_id: str | None = None, credentials: Any = None, schema_path: str = "schemas/sample_schema.csv") -> None:
    logger.info(f"Starting pipeline for APK: {apk_path}")
    settings = get_settings()
    if os.path.exists(settings.LOCAL_OUTPUT_PATH):
        try: os.remove(settings.LOCAL_OUTPUT_PATH)
        except Exception: pass
    writer = LocalExcelWriter()
    expected_events = SchemaReaderAgent(schema_path=schema_path).run()
    decompiled_sources = ApkDecompiler().decompile(apk_path)
    if not settings.ANDROID_APP_PACKAGE:
        manifest_path = os.path.join(os.path.dirname(decompiled_sources), "AndroidManifest.xml")
        if not os.path.exists(manifest_path):
            manifest_path = os.path.join(os.path.dirname(decompiled_sources), "resources", "AndroidManifest.xml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = re.search(r'package="([^"]+)"', f.read())
                if m: settings.ANDROID_APP_PACKAGE = m.group(1)
        if not settings.ANDROID_APP_PACKAGE: raise ValueError("ANDROID_APP_PACKAGE missing.")
    code_locations = CodebaseMapperAgent(decompiled_sources).run(expected_events)
    crawl_plans = CrawlPlannerAgent().run(expected_events)

    dev_conn = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        dev_conn = any(line.strip().endswith("\tdevice") for line in res.stdout.strip().split("\n")[1:])
    except Exception: pass

    if not dev_conn:
        logger.warning("No device connected. Running SYNTHETIC DRY RUN validation.")
        _run_synthetic_dry_run(expected_events, writer)
        return

    log_agent = LogCaptureAgent()
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "log.tag.FA", "VERBOSE"), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "log.tag.FA-SVC", "VERBOSE"), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "am", "force-stop", settings.ANDROID_APP_PACKAGE), capture_output=True)

    executor = CrawlExecutorAgent(apk_path=apk_path)
    screen_detector = ScreenDetector()
    orchestrator = RuntimeAuditOrchestrator(executor, log_agent, screen_detector, expected_events)

    events_and_plans = [(e, p) for p in crawl_plans for e in expected_events if e.event_name == p.event_name and e.screen == p.screen]
    all_captured_logs, all_telemetry, all_runtime = [], [], []
    tele_val, run_val = TelemetryValidatorAgent(), RuntimeValidatorAgent()

    try:
        captures = orchestrator.run_full_audit(events_and_plans)
        capture_map = {c.event_name: c for c in captures}
        for event, plan in events_and_plans:
            cap = capture_map.get(event.event_name)
            logs = cap.captured_logs if cap else []
            all_telemetry.append(tele_val.validate_event(event, logs))
            all_runtime.append(run_val.validate_execution(event.event_name, event.screen, plan, len(logs) > 0, event.user_action))
            if cap: all_captured_logs.extend(logs)
    finally:
        try: executor.quit()
        except Exception: pass

    telemetry_map = {(res.event_name, res.screen): res for res in all_telemetry}
    runtime_map = {(res.event_name, res.screen): res for res in all_runtime}
    for event in expected_events:
        key = (event.event_name, event.screen)
        if key not in telemetry_map: all_telemetry.append(tele_val.validate_event(event, []))
        if key not in runtime_map:
            all_runtime.append(run_val.validate_execution(event.event_name, event.screen, CrawlPlan(event_name=event.event_name, screen=event.screen, steps=[]), False, event.user_action))

    ValidationCombinerAgent().run(expected_events, all_telemetry, all_runtime, code_locations, writer)
    logger.info(f"Audit completed: {settings.LOCAL_OUTPUT_PATH}")

def _run_synthetic_dry_run(expected_events: list, writer: LocalExcelWriter) -> None:
    tele_val, run_val = TelemetryValidatorAgent(), RuntimeValidatorAgent()
    all_tele = tele_val.run(expected_events, [])
    all_run = [run_val.validate_execution(e.event_name, e.screen, CrawlPlan(event_name=e.event_name, screen=e.screen, steps=[]), False, e.user_action) for e in expected_events]
    ValidationCombinerAgent().run(expected_events, all_tele, all_run, [], writer)

if __name__ == "__main__":
    dev_conn = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        dev_conn = any(line.strip().endswith("\tdevice") for line in res.stdout.strip().split("\n")[1:])
    except Exception: pass

    if not dev_conn:
        print("This module requires a connected live Android device (adb devices).\nUsage pattern: python -m orchestrator <path_to_apk> [path_to_schema]")
        sys.exit(0)
    else:
        print("Live device connected.\nA full standalone demo requires a real APK path and ANDROID_APP_PACKAGE.\nPlease run this audit from the Streamlit UI or pass the correct CLI arguments.")
