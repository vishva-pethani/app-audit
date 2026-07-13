"""
Orchestrator:
Coordinates the execution of all 8 agents in the App Tag Auditor pipeline.
"""
import os
import re
import sys
import time
import subprocess
from datetime import datetime
from typing import Any
from core.logger import get_logger
from core.config import get_settings
from core.output_writer import LocalExcelWriter
from core.apk_decompiler import ApkDecompiler
from core.screen_detector import ScreenDetector
from core.models import EventRuntimeCapture, ExpectedEvent, CrawlPlan
from agents.agent1_schema_reader import SchemaReaderAgent
from agents.agent2_codebase_mapper import CodebaseMapperAgent
from agents.agent3_crawl_planner import CrawlPlannerAgent
from agents.agent4_crawl_executor import CrawlExecutorAgent
from agents.agent5_log_capture import LogCaptureAgent
from agents.agent6_telemetry_validator import TelemetryValidatorAgent
from agents.agent7_runtime_validator import RuntimeValidatorAgent
from agents.agent8_validation_combiner import ValidationCombinerAgent
import logging
from agents.agent1b_ecom_schema_reader import EcomSchemaReaderAgent
from agents.agent3b_ecom_crawl_planner import EcomCrawlPlannerAgent
from agents.agent5b_ecom_log_capture import EcomLogCaptureAgent
from agents.agent6b_ecom_telemetry_validator import EcomTelemetryValidatorAgent
from agents.agent7b_ecom_runtime_validator import EcomRuntimeValidatorAgent
from agents.agent8b_ecom_validation_combiner import EcomValidationCombinerAgent
from core.models import (ExpectedEcomEvent, CapturedEcomLog, FinalEcomAuditRow,
                         EcomTelemetryValidationResult, EcomRuntimeValidationResult)

logger = get_logger(__name__)

class RuntimeAuditOrchestrator:
    def __init__(self, crawl_executor, log_agent, screen_detector: ScreenDetector, all_events: list[ExpectedEvent]):
        self.crawl_executor = crawl_executor
        self.log_agent = log_agent
        self.screen_detector = screen_detector
        self.all_events = all_events

    def run_single_event(self, event: ExpectedEvent, plan: CrawlPlan) -> EventRuntimeCapture:
        settings = get_settings()
        all_names = {e.event_name for e in self.all_events}
        self.log_agent.start_capture(all_names)
        self.crawl_executor.execute_plan(plan, event=event)
        # Only query the screen detector if the session is alive — avoids
        # "cannot be proxied" errors flooding the log after a crash.
        session_alive = not getattr(self.crawl_executor, '_session_dead', False) and self.crawl_executor.driver is not None
        detected_screen_immediately, detection_source_immediate = (
            self.screen_detector.detect(self.crawl_executor.driver)
            if session_alive
            else (None, "unknown")
        )
        # best-effort: timestamp right after the plan's final step completes (approximate true device-side firing moment)
        trigger_timestamp = datetime.now().isoformat()
        if session_alive:
            time.sleep(settings.RUNTIME_CAPTURE_BUFFER_SECONDS)
        detected_screen, source = (
            self.screen_detector.detect(self.crawl_executor.driver)
            if session_alive
            else (None, "unknown")
        )
        self.log_agent.stop_capture()
        logs = self.log_agent.get_captured_logs()
        # Convert CapturedLog instances to dicts before constructing EventRuntimeCapture.
        # Streamlit's module hot-reload can create a second CapturedLog class identity,
        # causing Pydantic v2 to reject valid instances. Dicts are always accepted.
        logs_as_dicts = [l.model_dump() if hasattr(l, 'model_dump') else dict(l) for l in logs]
        return EventRuntimeCapture(
            event_name=event.event_name,
            trigger_timestamp=trigger_timestamp,
            captured_logs=logs_as_dicts,
            detected_screen_after=detected_screen,
            detection_source=source,
            detected_screen_immediately=detected_screen_immediately,
            detection_source_immediate=detection_source_immediate
        )

    def reset_best_effort(self) -> None:
        """
        Best-effort screen reset between events.
        Navigates back to the main screen without relaunching the app.
        Skips gracefully if the session is known to be dead.
        """
        driver = self.crawl_executor.driver
        if getattr(self.crawl_executor, '_session_dead', False):
            logger.warning("Session is dead — skipping reset_best_effort (recovery will happen at next execute_plan).")
            return
        if driver is not None:
            logger.info("Navigating back to main screen between events...")
            try:
                self.crawl_executor._ensure_on_main_screen()
            except Exception as e:
                logger.warning(f"Failed to ensure on main screen between events: {e}")

    def run_full_audit(self, events_and_plans: list[tuple[ExpectedEvent, CrawlPlan]]) -> list[EventRuntimeCapture]:
        captures = []
        total = len(events_and_plans)
        for i, (event, plan) in enumerate(events_and_plans):
            logger.info(f"Running audit: event {i+1} of {total} ({event.event_name})")
            cap = self.run_single_event(event, plan)
            captures.append(cap)
            if i < total - 1:
                self.reset_best_effort()
        return captures


class EcomAuditOrchestrator:
    def __init__(self, crawl_executor, ecom_log_agent: EcomLogCaptureAgent,
                 all_events: list[ExpectedEcomEvent]):
        self.crawl_executor = crawl_executor
        self.ecom_log_agent = ecom_log_agent
        self.all_events = all_events
        self.logger = get_logger(__name__)
        self._telemetry_validator = EcomTelemetryValidatorAgent()
        self._runtime_validator   = EcomRuntimeValidatorAgent()
        self._combiner            = EcomValidationCombinerAgent()

    def run_single_event(self, event: ExpectedEcomEvent,
                         plan: CrawlPlan) -> FinalEcomAuditRow:
        if not plan.navigation_resolved:
            self.logger.warning(
                f"Skipping ecom event '{event.event_name}' — crawl plan unresolved. "
                f"Fill in ecom_crawl_map.json to enable this event."
            )
            telemetry = EcomTelemetryValidationResult(
                event_name=event.event_name, passed=False,
                missing_event_keys=event.event_param_names,
                extra_event_keys=[], mismatched_event_keys=[],
                item_count_found=0, item_count_expected_min=event.min_items,
                item_count_passed=False,
                items_with_missing_keys=[], items_with_type_errors=[],
                items_with_custom_params=[], items_with_discount_revenue_errors=[]
            )
            runtime = EcomRuntimeValidationResult(
                event_name=event.event_name, passed=False,
                fire_count=0, not_implemented=True, double_fired=False,
                notes="Crawl plan unresolved — event was not triggered."
            )
            return self._combiner.combine_event(event, telemetry, runtime,
                                                crawl_resolved=False)

        ecom_names = {e.event_name for e in self.all_events}
        self.ecom_log_agent.start_capture(ecom_names)

        try:
            self.crawl_executor.execute_plan(plan)
        except Exception as e:
            self.logger.error(f"Crawl execution failed for '{event.event_name}': {e}")

        time.sleep(get_settings().RUNTIME_CAPTURE_BUFFER_SECONDS)
        self.ecom_log_agent.stop_capture()
        captured_logs = self.ecom_log_agent.get_captured_logs()

        self.logger.info(
            f"Captured {len(captured_logs)} ecom log(s) for '{event.event_name}'."
        )

        telemetry = self._telemetry_validator.validate_event(event, captured_logs)
        runtime   = self._runtime_validator.validate_event(event, captured_logs)
        return self._combiner.combine_event(event, telemetry, runtime,
                                            crawl_resolved=True)

    def reset_best_effort(self) -> None:
        if self.crawl_executor.driver is None:
            return
        for attempt in range(3):
            try:
                self.crawl_executor.driver.back()
                time.sleep(1)
            except Exception as e:
                self.logger.warning(f"Reset attempt {attempt+1} failed: {e}")
                break

    def run_full_audit(self, events: list[ExpectedEcomEvent],
                       plans: list[CrawlPlan],
                       log_callback=None) -> list[FinalEcomAuditRow]:
        plan_lookup = {p.event_name: p for p in plans}
        rows = []
        for i, event in enumerate(events):
            plan = plan_lookup.get(event.event_name)
            if plan is None:
                self.logger.error(
                    f"No plan for ecom event '{event.event_name}' — skipping."
                )
                continue
            msg = f"Running ecom audit: event {i+1} of {len(events)} ({event.event_name})"
            self.logger.info(msg)
            if log_callback: log_callback(msg)
            row = self.run_single_event(event, plan)
            rows.append(row)
            if i < len(events) - 1:
                self.reset_best_effort()
        return rows


def run_pipeline(apk_path: str, sheet_id: str | None = None, credentials: Any = None, schema_path: str = "schemas/sample_schema.csv", interaction_bridge=None) -> None:
    logger.info(f"Starting pipeline for APK: {apk_path}")
    settings = get_settings()
    if os.path.exists(settings.LOCAL_OUTPUT_PATH):
        try:
            os.remove(settings.LOCAL_OUTPUT_PATH)
        except Exception as e:
            logger.warning(f"Could not clear old output report: {e}")
            
    writer = LocalExcelWriter()
    expected_events = SchemaReaderAgent(schema_path=schema_path).run()
    decompiled_sources = ApkDecompiler().decompile(apk_path)
    
    if not settings.ANDROID_APP_PACKAGE:
        # Search all candidate locations for AndroidManifest.xml under the decompiled cache dir.
        # decompiled_sources is typically <cache_dir>/sources; the manifest lives in <cache_dir>/resources/.
        cache_dir = os.path.dirname(decompiled_sources)
        candidate_manifests = [
            os.path.join(cache_dir, "AndroidManifest.xml"),
            os.path.join(cache_dir, "resources", "AndroidManifest.xml"),
            os.path.join(decompiled_sources, "AndroidManifest.xml"),
        ]
        # Also do a recursive search under cache_dir as a last resort
        for root, _, files in os.walk(cache_dir):
            for fname in files:
                if fname == "AndroidManifest.xml":
                    candidate_manifests.append(os.path.join(root, fname))

        for manifest_path in candidate_manifests:
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    match = re.search(r'package="([^"]+)"', content)
                    if match:
                        pkg = match.group(1)
                        # Ignore generic Android framework manifests
                        if pkg and not pkg.startswith("android"):
                            settings.ANDROID_APP_PACKAGE = pkg
                            logger.info(f"Auto-detected ANDROID_APP_PACKAGE: {pkg} (from {manifest_path})")
                            break
                except Exception as e:
                    logger.warning(f"Failed to read manifest at {manifest_path}: {e}")

        if not settings.ANDROID_APP_PACKAGE:
            raise ValueError(
                "ANDROID_APP_PACKAGE could not be auto-detected from the APK. "
                "Please set it manually in your .env file (e.g. ANDROID_APP_PACKAGE=com.example.app)."
            )
            
    code_locations = CodebaseMapperAgent(decompiled_sources).run(expected_events)
    crawl_plans = CrawlPlannerAgent().run(expected_events)

    device_connected = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        device_connected = any(line.strip().endswith("\tdevice") for line in res.stdout.strip().split("\n")[1:])
    except Exception:
        pass

    if not device_connected:
        logger.warning("No device connected. Running SYNTHETIC DRY RUN validation.")
        _run_synthetic_dry_run(expected_events, writer)
        return

    log_agent = LogCaptureAgent()
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "log.tag.FA", "VERBOSE"), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "log.tag.FA-SVC", "VERBOSE"), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "debug.firebase.analytics.app", settings.ANDROID_APP_PACKAGE), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "am", "force-stop", settings.ANDROID_APP_PACKAGE), capture_output=True)

    executor = CrawlExecutorAgent(apk_path=apk_path, app_package=settings.ANDROID_APP_PACKAGE, interaction_bridge=interaction_bridge)
    screen_detector = ScreenDetector()
    orchestrator = RuntimeAuditOrchestrator(executor, log_agent, screen_detector, expected_events)

    # Build a 1:1 mapping: each plan paired with its exact matching event.
    # The old list-comprehension produced a cartesian product (N×M pairs) when
    # there were multiple events/plans with the same name but different screens,
    # resulting in e.g. 202 pairs for 20 events.  A dict keyed by (event_name,
    # screen) guarantees at most one pair per event.
    plan_map = {(p.event_name, p.screen): p for p in crawl_plans}
    events_and_plans = [
        (e, plan_map[(e.event_name, e.screen)])
        for e in expected_events
        if (e.event_name, e.screen) in plan_map
    ]
    tele_val, run_val = TelemetryValidatorAgent(), RuntimeValidatorAgent()
    all_telemetry, all_runtime = [], []

    try:
        captures = orchestrator.run_full_audit(events_and_plans)
        for (event, plan), cap in zip(events_and_plans, captures):
            logs = cap.captured_logs if cap else []
            all_telemetry.append(tele_val.validate_event(event, logs))
            all_runtime.append(run_val.validate_execution(event.event_name, event.screen, plan, cap is not None, event.user_action))
    finally:
        try:
            executor.quit()
        except Exception:
            pass

    telemetry_map = {(res.event_name, res.screen): res for res in all_telemetry}
    runtime_map = {(res.event_name, res.screen): res for res in all_runtime}
    for event in expected_events:
        key = (event.event_name, event.screen)
        if key not in telemetry_map:
            all_telemetry.append(tele_val.validate_event(event, []))
        if key not in runtime_map:
            all_runtime.append(run_val.validate_execution(event.event_name, event.screen, CrawlPlan(event_name=event.event_name, screen=event.screen, steps=[]), False, event.user_action))

    ValidationCombinerAgent().run(expected_events, all_telemetry, all_runtime, code_locations, writer)
    logger.info(f"Audit pipeline completed. Results written to: {settings.LOCAL_OUTPUT_PATH}")

def _run_synthetic_dry_run(expected_events: list, writer: LocalExcelWriter) -> None:
    from core.models import CapturedLog, CrawlStep
    mock_logs = [
        CapturedLog(event_name="screen_view", raw_params={"screenname": "My_RE_screen"}, timestamp=datetime.now().isoformat(), source="logcat"),
        CapturedLog(event_name="add_motorcycle", raw_params={"screenname": "My_RE_screen"}, timestamp=datetime.now().isoformat(), source="logcat"),
        CapturedLog(event_name="book_service", raw_params={"clickText": "Book Now", "modelName": "Super Meteor 650", "sectionHeading": "Service Booking", "screenname": "My_RE_screen"}, timestamp=datetime.now().isoformat(), source="logcat")
    ]
    tele_val, run_val = TelemetryValidatorAgent(), RuntimeValidatorAgent()
    all_tele = tele_val.run(expected_events, mock_logs)
    all_run = [run_val.validate_execution(e.event_name, e.screen, CrawlPlan(event_name=e.event_name, screen=e.screen, steps=[CrawlStep(action_type="tap", target_selector="Mock", step_order=0)]), True, e.user_action) for e in expected_events]
    ValidationCombinerAgent().run(expected_events, all_tele, all_run, [], writer)


def run_ecom_pipeline(apk_path: str, log_callback=None) -> None:
    def _log(msg: str):
        logging.getLogger(__name__).info(msg)
        if log_callback: log_callback(msg)

    try:
        _log("Loading GA4 ecommerce event config (14 events)...")
        events = EcomSchemaReaderAgent().run()
        _log(f"Loaded {len(events)} ecom events.")

        _log("Building ecom crawl plans from ecom_crawl_map.json...")
        plans = EcomCrawlPlannerAgent().run(events)
        resolved = sum(1 for p in plans if p.navigation_resolved)
        _log(f"Crawl plans: {resolved} resolved, {len(plans)-resolved} skipped "
             f"(fill in ecom_crawl_map.json to enable skipped events).")

        _log("Connecting to Appium and initialising crawl executor...")
        
        settings = get_settings()
        if not settings.ANDROID_APP_PACKAGE:
            _log("ANDROID_APP_PACKAGE not defined in settings. Attempting auto-detection...")
            detected_pkg = None
            
            # Strategy 1: Try aapt
            try:
                res = subprocess.run(["aapt", "dump", "badging", apk_path], capture_output=True, text=True, errors="ignore")
                if res.returncode == 0:
                    match = re.search(r"package: name='([^']+)'", res.stdout)
                    if match:
                        detected_pkg = match.group(1)
            except Exception:
                pass

            # Strategy 2: Try JADX manifest parsing
            if not detected_pkg:
                _log("aapt auto-detection failed. Attempting JADX decompilation to parse AndroidManifest.xml...")
                try:
                    decompiled_sources = ApkDecompiler().decompile(apk_path)
                    cache_dir = os.path.dirname(decompiled_sources)
                    candidate_manifests = [
                        os.path.join(cache_dir, "AndroidManifest.xml"),
                        os.path.join(cache_dir, "resources", "AndroidManifest.xml"),
                        os.path.join(decompiled_sources, "AndroidManifest.xml"),
                    ]
                    for root, _, files in os.walk(cache_dir):
                        for fname in files:
                            if fname == "AndroidManifest.xml":
                                candidate_manifests.append(os.path.join(root, fname))

                    for manifest_path in candidate_manifests:
                        if os.path.exists(manifest_path):
                            with open(manifest_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            match = re.search(r'package="([^"]+)"', content)
                            if match:
                                pkg = match.group(1)
                                if pkg and not pkg.startswith("android"):
                                    detected_pkg = pkg
                                    break
                except Exception as e:
                    _log(f"JADX decompilation failed: {e}")

            if detected_pkg:
                settings.ANDROID_APP_PACKAGE = detected_pkg
                _log(f"Successfully auto-detected ANDROID_APP_PACKAGE: {detected_pkg}")
            else:
                raise ValueError(
                    "ANDROID_APP_PACKAGE could not be auto-detected from the APK. "
                    "Please set it manually in your .env file (e.g. ANDROID_APP_PACKAGE=com.example.app)."
                )

        crawl_executor = CrawlExecutorAgent(apk_path=apk_path, app_package=settings.ANDROID_APP_PACKAGE)
        crawl_executor._build_driver()

        ecom_log_agent = EcomLogCaptureAgent()
        orchestrator   = EcomAuditOrchestrator(crawl_executor, ecom_log_agent, events)

        _log("Starting ecom audit run...")
        rows = orchestrator.run_full_audit(events, plans, log_callback=log_callback)

        _log("Writing ecom results to output file...")
        output_path = EcomValidationCombinerAgent().write_to_output(rows)
        _log(f"Ecom audit complete. Results written to: {output_path}")

    except Exception as e:
        msg = f"Ecom pipeline failed: {e}"
        logging.getLogger(__name__).error(msg, exc_info=True)
        if log_callback: log_callback(msg)
        raise
    finally:
        try:
            crawl_executor.quit()
        except Exception:
            pass


if __name__ == "__main__":
    device_connected = False
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        device_connected = any(line.strip().endswith("\tdevice") for line in res.stdout.strip().split("\n")[1:])
    except Exception:
        pass
    if not device_connected:
        print("This requires a live device. Usage: python -m orchestrator <path_to_apk> [path_to_schema]")
        sys.exit(0)
    else:
        print("A full standalone demo here would require a real APK path and ANDROID_APP_PACKAGE.")
        print("This will be exercised properly once wired into the frontend / a future end-to-end script.")
