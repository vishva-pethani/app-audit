"""
Agent8 ValidationCombinerAgent:
Merges TelemetryValidationResult + RuntimeValidationResult per event into a final,
consolidated FinalAuditRow, and writes the results to output Excel sheets.
"""

import os
from datetime import datetime
from typing import Literal
import core.logger
from core.models import ExpectedEvent, TelemetryValidationResult, RuntimeValidationResult, FinalAuditRow

class ValidationCombinerAgent:
    def __init__(self):
        self.logger = core.logger.get_logger(__name__)

    def _build_details(self, telemetry: TelemetryValidationResult, runtime: RuntimeValidationResult) -> str:
        clauses = []
        if telemetry.missing_keys:
            clauses.append(f"Missing params: {', '.join(telemetry.missing_keys)}.")
        if telemetry.extra_keys:
            clauses.append(f"Extra params: {', '.join(telemetry.extra_keys)}.")
        if telemetry.mismatched_keys:
            clauses.append(f"Incorrect values: {', '.join(telemetry.mismatched_keys)}.")
        if runtime.not_implemented:
            clauses.append("Event never fired.")
        if runtime.double_fired:
            clauses.append(f"Fired {runtime.fire_count} times, expected once.")
        if runtime.screen_check_status == "incorrect":
            clauses.append("Fired on the wrong screen.")
        if runtime.screen_check_status == "unknown":
            clauses.append("Screen identity inconclusive — manual check recommended.")
        if runtime.unexpected_co_fired_events:
            clauses.append(f"Unexpected co-fired event(s): {', '.join(runtime.unexpected_co_fired_events)}.")

        if not clauses:
            return "All checks passed."
        return " ".join(clauses)

    def _determine_overall_status(self, telemetry: TelemetryValidationResult, runtime: RuntimeValidationResult) -> Literal["PASS", "FAIL", "PARTIAL"]:
        if telemetry.passed and runtime.passed:
            return "PARTIAL" if runtime.screen_check_status == "unknown" else "PASS"
        if (not telemetry.passed) and (not runtime.passed):
            return "FAIL"
        return "PARTIAL"

    def combine_event(self, event: ExpectedEvent, telemetry: TelemetryValidationResult, runtime: RuntimeValidationResult) -> FinalAuditRow:
        overall = self._determine_overall_status(telemetry, runtime)
        details = self._build_details(telemetry, runtime)
        return FinalAuditRow(
            event_name=event.event_name,
            screen=event.screen,
            telemetry_passed=telemetry.passed,
            runtime_passed=runtime.passed,
            overall_status=overall,
            details=details,
            timestamp=datetime.now().isoformat()
        )

    def run(
        self,
        expected_events: list[ExpectedEvent],
        telemetry_results: list[TelemetryValidationResult],
        runtime_results: list[RuntimeValidationResult],
        code_locations: list = None,
        output_writer = None
    ) -> list[FinalAuditRow]:
        telemetry_dict = {r.event_name: r for r in telemetry_results}
        runtime_dict = {r.event_name: r for r in runtime_results}
        
        final_rows = []
        for event in expected_events:
            telemetry = telemetry_dict.get(event.event_name)
            runtime = runtime_dict.get(event.event_name)
            if not telemetry or not runtime:
                self.logger.error(f"Missing results for event: {event.event_name}. Telemetry: {telemetry is not None}, Runtime: {runtime is not None}")
                continue
            row = self.combine_event(event, telemetry, runtime)
            final_rows.append(row)

        pass_count = sum(1 for r in final_rows if r.overall_status == "PASS")
        fail_count = sum(1 for r in final_rows if r.overall_status == "FAIL")
        partial_count = sum(1 for r in final_rows if r.overall_status == "PARTIAL")
        self.logger.info(f"Audit summary: PASS: {pass_count}, FAIL: {fail_count}, PARTIAL: {partial_count}")

        if output_writer is not None:
            self.write_to_output(final_rows, output_writer)

        return final_rows

    def write_to_output(self, rows: list[FinalAuditRow], output_writer, tab_name: str = "FinalAudit") -> None:
        headers = ["event_name", "screen", "telemetry_passed", "runtime_passed", "overall_status", "details", "timestamp"]
        output_writer.ensure_headers(tab_name, headers)
        for row in rows:
            output_writer.append_row(tab_name, row.model_dump())

if __name__ == "__main__":
    import json
    from core.output_writer import LocalExcelWriter

    # Define test events
    all_events = [
        ExpectedEvent(
            event_name="screen_view", screen="My_RE_screen", user_action="lands on My RE screen", expected_params=[], raw_principle="", keywords=[]
        ),
        ExpectedEvent(
            event_name="add_motorcycle", screen="My_RE_screen", user_action="clicks Add icon", expected_params=[], raw_principle="", keywords=[]
        ),
        ExpectedEvent(
            event_name="book_service", screen="My_RE_screen", user_action="clicks Book Now", expected_params=[], raw_principle="", keywords=[]
        ),
        ExpectedEvent(
            event_name="view_service_history", screen="My_RE_screen", user_action="clicks My Service History", expected_params=[], raw_principle="", keywords=[]
        )
    ]

    combiner = ValidationCombinerAgent()

    # a. screen_view - PASS
    tele_a = TelemetryValidationResult(event_name="screen_view", screen="My_RE_screen", passed=True)
    run_a = RuntimeValidationResult(
        event_name="screen_view", screen="My_RE_screen", passed=True, expected_trigger="lands on My RE screen",
        actual_trigger_observed=True, notes="", fire_count=1, screen_check_status="correct"
    )
    res_a = combiner.combine_event(all_events[0], tele_a, run_a)
    print("Expected: PASS")
    print(res_a.model_dump_json(indent=2))
    print("=" * 60)

    # b. add_motorcycle - PARTIAL
    tele_b = TelemetryValidationResult(event_name="add_motorcycle", screen="My_RE_screen", passed=True)
    run_b = RuntimeValidationResult(
        event_name="add_motorcycle", screen="My_RE_screen", passed=False, expected_trigger="clicks Add icon",
        actual_trigger_observed=True, notes="", fire_count=2, double_fired=True, screen_check_status="correct"
    )
    res_b = combiner.combine_event(all_events[1], tele_b, run_b)
    print("Expected: PARTIAL")
    print(res_b.model_dump_json(indent=2))
    print("=" * 60)

    # c. book_service - FAIL
    tele_c = TelemetryValidationResult(event_name="book_service", screen="My_RE_screen", passed=False, missing_keys=["clickText"])
    run_c = RuntimeValidationResult(
        event_name="book_service", screen="My_RE_screen", passed=False, expected_trigger="clicks Book Now",
        actual_trigger_observed=False, notes="", fire_count=0, not_implemented=True, screen_check_status="correct"
    )
    res_c = combiner.combine_event(all_events[2], tele_c, run_c)
    print("Expected: FAIL")
    print(res_c.model_dump_json(indent=2))
    print("=" * 60)

    # d. view_service_history - PARTIAL
    tele_d = TelemetryValidationResult(event_name="view_service_history", screen="My_RE_screen", passed=False, mismatched_keys=["screenname"])
    run_d = RuntimeValidationResult(
        event_name="view_service_history", screen="My_RE_screen", passed=True, expected_trigger="clicks My Service History",
        actual_trigger_observed=True, notes="", fire_count=1, screen_check_status="correct"
    )
    res_d = combiner.combine_event(all_events[3], tele_d, run_d)
    print("Expected: PARTIAL")
    print(res_d.model_dump_json(indent=2))
    print("=" * 60)

    # e. add_motorcycle (reuse, second scenario) - PARTIAL
    tele_e = TelemetryValidationResult(event_name="add_motorcycle", screen="My_RE_screen", passed=True)
    run_e = RuntimeValidationResult(
        event_name="add_motorcycle", screen="My_RE_screen", passed=True, expected_trigger="clicks Add icon",
        actual_trigger_observed=True, notes="", fire_count=1, screen_check_status="unknown"
    )
    res_e = combiner.combine_event(all_events[1], tele_e, run_e)
    print("Expected: PARTIAL")
    print(res_e.model_dump_json(indent=2))
    print("=" * 60)

    # Demonstrate write_to_output()
    os.makedirs("./tmp", exist_ok=True)
    temp_file = "./tmp/test_combiner_results.xlsx"
    temp_writer = LocalExcelWriter(temp_file)

    results = [res_a, res_b, res_c, res_d, res_e]
    combiner.write_to_output(results, temp_writer)

    print("\nRead back rows:")
    for row in temp_writer.read_all("FinalAudit"):
        print(row)

    if os.path.exists(temp_file):
        os.remove(temp_file)
