"""
Orchestrator:
Coordinates the execution of all 8 agents in the App Tag Auditor pipeline.
"""
import os
import re
import sys
import time
import queue
import subprocess
from datetime import datetime
from typing import Any
from core.logger import get_logger
from core.config import get_settings
from core.output_writer import LocalExcelWriter
from core.apk_decompiler import ApkDecompiler
from agents.agent1_schema_reader import SchemaReaderAgent
from agents.agent2_codebase_mapper import CodebaseMapperAgent
from agents.agent3_crawl_planner import CrawlPlannerAgent
from agents.agent4_crawl_executor import CrawlExecutorAgent
from agents.agent5_log_capture import LogCaptureAgent
from agents.agent6_telemetry_validator import TelemetryValidatorAgent
from agents.agent7_runtime_validator import RuntimeValidatorAgent
from agents.agent8_validation_combiner import ValidationCombinerAgent

logger = get_logger(__name__)

def run_pipeline(apk_path: str, sheet_id: str | None = None, credentials: Any = None, schema_path: str = "schemas/sample_schema.csv") -> None:
    logger.info(f"Starting pipeline for APK: {apk_path}")
    settings = get_settings()
    
    # Reset/clear previous output report to start fresh
    if os.path.exists(settings.LOCAL_OUTPUT_PATH):
        try:
            os.remove(settings.LOCAL_OUTPUT_PATH)
            logger.info(f"Cleared previous output report at {settings.LOCAL_OUTPUT_PATH}")
        except Exception as e:
            logger.warning(f"Could not clear old output report: {e}")
            
    writer = LocalExcelWriter()

    # Step 1: Schema Ingestion (Agent 1)
    expected_events = SchemaReaderAgent(schema_path=schema_path).run()

    # Step 2: Codebase Mapping (Agent 2)
    decompiled_sources = ApkDecompiler().decompile(apk_path)
    if not settings.ANDROID_APP_PACKAGE:
        manifest_path = os.path.join(os.path.dirname(decompiled_sources), "AndroidManifest.xml")
        if not os.path.exists(manifest_path):
            manifest_path = os.path.join(os.path.dirname(decompiled_sources), "resources", "AndroidManifest.xml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                match = re.search(r'package="([^"]+)"', f.read())
                if match:
                    settings.ANDROID_APP_PACKAGE = match.group(1)
        if not settings.ANDROID_APP_PACKAGE:
            raise ValueError("ANDROID_APP_PACKAGE is missing in .env and not found in manifest.")
            
    code_locations = CodebaseMapperAgent(decompiled_sources).run(expected_events)
    writer.ensure_headers("CodebaseMapping", ["event_name", "file_path", "line_number", "matched_snippet", "breadcrumb", "confidence"])
    for loc in code_locations:
        writer.append_row("CodebaseMapping", {
            "event_name": loc.event_name, "file_path": loc.file_path, "line_number": loc.line_number,
            "matched_snippet": loc.matched_snippet, "breadcrumb": ", ".join(loc.breadcrumb), "confidence": loc.confidence
        })

    # Step 3: Crawl Planning (Agent 3)
    crawl_plans = CrawlPlannerAgent().run(expected_events)

    # Check device connection
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

    # Step 4 & 5: Execution + Log Capture
    all_captured_logs, all_telemetry, all_runtime = [], [], []
    log_agent = LogCaptureAgent()
    
    # Configure Android system properties to enable verbose Firebase Analytics logs
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "log.tag.FA", "VERBOSE"), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "log.tag.FA-SVC", "VERBOSE"), capture_output=True)
    subprocess.run(log_agent._adb_cmd("shell", "setprop", "debug.firebase.analytics.app", settings.ANDROID_APP_PACKAGE), capture_output=True)
    # Force stop the app so it restarts with the new debug configurations active
    subprocess.run(log_agent._adb_cmd("shell", "am", "force-stop", settings.ANDROID_APP_PACKAGE), capture_output=True)

    tele_val, run_val = TelemetryValidatorAgent(), RuntimeValidatorAgent()
    expected_names = {e.event_name for e in expected_events}

    executor = CrawlExecutorAgent(apk_path=apk_path)
    try:
        for plan in crawl_plans:
            matching_event = next((e for e in expected_events if e.event_name == plan.event_name), None)
            if not matching_event:
                continue

            log_agent.start_capture()
            
            # Restart the app fresh on the device before executing the next scenario
            # (only if driver has already been built on a previous iteration)
            if executor.driver is not None:
                logger.info(f"Relaunching app {settings.ANDROID_APP_PACKAGE} to start scenario '{plan.event_name}' fresh...")
                try:
                    executor.driver.terminate_app(settings.ANDROID_APP_PACKAGE)
                    time.sleep(1)
                    executor.driver.activate_app(settings.ANDROID_APP_PACKAGE)
                    time.sleep(4)
                    executor._ensure_on_main_screen()
                except Exception as e:
                    logger.warning(f"Error restarting app between plans: {e}")

            exec_ok = False
            try:
                exec_ok = executor.execute_plan(plan)
            except Exception as e:
                logger.error(f"Execution error for plan {plan.event_name}: {e}")
            
            # Allow final analytics logs to flush to the adb buffer
            time.sleep(3)
            log_agent.stop_capture()

            captured_for_plan = []
            while not log_agent._queue.empty():
                try:
                    line = log_agent._queue.get_nowait()
                    log = log_agent._parse_line(line)
                    if log and log.event_name in expected_names:
                        captured_for_plan.append(log)
                except queue.Empty:
                    break
            
            all_captured_logs.extend(captured_for_plan)
            all_telemetry.append(tele_val.validate_event(matching_event, captured_for_plan))
            all_runtime.append(run_val.validate_execution(plan.event_name, plan, exec_ok, matching_event.user_action))
    finally:
        executor.quit()

    log_agent.write_logs_to_output(all_captured_logs, writer)
    ValidationCombinerAgent().run(expected_events, all_telemetry, all_runtime, code_locations, writer)
    logger.info(f"Audit pipeline completed. Results written to: {settings.LOCAL_OUTPUT_PATH}")

def _run_synthetic_dry_run(expected_events: list, writer: LocalExcelWriter) -> None:
    from core.models import CapturedLog, CrawlPlan, CrawlStep
    mock_logs = [
        CapturedLog(event_name="screen_view", raw_params={"screenname": "My_RE_screen"}, timestamp=datetime.now().isoformat(), source="logcat"),
        CapturedLog(event_name="add_motorcycle", raw_params={"screenname": "My_RE_screen"}, timestamp=datetime.now().isoformat(), source="logcat"),
        CapturedLog(event_name="book_service", raw_params={"clickText": "Book Now", "modelName": "Super Meteor 650", "sectionHeading": "Service Booking", "screenname": "My_RE_screen"}, timestamp=datetime.now().isoformat(), source="logcat")
    ]
    log_agent = LogCaptureAgent()
    log_agent.write_logs_to_output(mock_logs, writer)

    tele_val, run_val = TelemetryValidatorAgent(), RuntimeValidatorAgent()
    all_tele = tele_val.run(expected_events, mock_logs)
    
    all_run = []
    for e in expected_events:
        mock_plan = CrawlPlan(event_name=e.event_name, steps=[CrawlStep(action_type="tap", target_selector="Mock", step_order=0)])
        all_run.append(run_val.validate_execution(e.event_name, mock_plan, True, e.user_action))
    
    ValidationCombinerAgent().run(expected_events, all_tele, all_run, [], writer)
    logger.info("Synthetic validation completed.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m orchestrator <path_to_apk> [path_to_schema]")
        sys.exit(1)
    apk = sys.argv[1]
    schema = sys.argv[2] if len(sys.argv) > 2 else "schemas/sample_schema.csv"
    run_pipeline(apk_path=apk, schema_path=schema)
