"""
Agent8 ValidationCombinerAgent:
Merges TelemetryValidationResult + RuntimeValidationResult per event into a final,
consolidated FinalAuditRow, and writes the results to output Excel sheets.
"""

from datetime import datetime
from core.logger import get_logger
from core.models import ExpectedEvent, TelemetryValidationResult, RuntimeValidationResult, FinalAuditRow

logger = get_logger(__name__)

class ValidationCombinerAgent:
    """
    Agent8 ValidationCombinerAgent:
    Aggregates runtime and telemetry validations into a final consolidated Excel worksheet.
    """
    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def combine(
        self,
        event: ExpectedEvent,
        telemetry: TelemetryValidationResult | None,
        runtime: RuntimeValidationResult | None
    ) -> FinalAuditRow:
        """
        Combines telemetry and runtime validations for a single event.
        """
        telemetry_passed = telemetry.passed if telemetry else False
        runtime_passed = runtime.passed if runtime else False

        # Status resolution logic
        if telemetry_passed and runtime_passed:
            overall_status = "PASS"
            details = "All checks passed. UI interaction succeeded and telemetry matched schema."
        elif not telemetry_passed and not runtime_passed:
            overall_status = "FAIL"
            details = "Both UI interaction and telemetry validation failed."
        else:
            overall_status = "PARTIAL"
            details = "Partial success. "

        detail_parts = []
        if telemetry:
            if not telemetry.passed:
                errs = []
                if telemetry.missing_keys:
                    errs.append(f"Missing params: {', '.join(telemetry.missing_keys)}")
                if telemetry.mismatched_keys:
                    errs.append(f"Mismatched params: {', '.join(telemetry.mismatched_keys)}")
                detail_parts.append(f"Telemetry issue ({'; '.join(errs)})" if errs else "Telemetry failed validation")
        else:
            detail_parts.append("Telemetry was not captured")

        if runtime:
            if not runtime.passed:
                detail_parts.append(f"UI execution issue ({runtime.notes})")
            else:
                detail_parts.append(f"UI execution success ({runtime.notes})")
        else:
            detail_parts.append("UI execution details missing")

        if detail_parts:
            details += " | ".join(detail_parts)

        return FinalAuditRow(
            event_name=event.event_name,
            screen=event.screen,
            telemetry_passed=telemetry_passed,
            runtime_passed=runtime_passed,
            overall_status=overall_status,
            details=details,
            timestamp=datetime.now().isoformat()
        )

    def run(
        self,
        expected_events: list[ExpectedEvent],
        telemetry_results: list[TelemetryValidationResult],
        runtime_results: list[RuntimeValidationResult],
        output_writer,
        tab_name: str = "FinalAudit"
    ) -> list[FinalAuditRow]:
        """
        Combines results and writes them to the specified worksheet tab.
        """
        logger.info(f"Combining validation results for {len(expected_events)} events...")
        
        telemetry_map = {res.event_name: res for res in telemetry_results}
        runtime_map = {res.event_name: res for res in runtime_results}

        final_rows = []
        for event in expected_events:
            telemetry = telemetry_map.get(event.event_name)
            runtime = runtime_map.get(event.event_name)
            
            row = self.combine(event, telemetry, runtime)
            final_rows.append(row)

        # Write to OutputWriter
        output_writer.ensure_headers(
            tab_name,
            ["event_name", "screen", "telemetry_passed", "runtime_passed", "overall_status", "details", "timestamp"]
        )

        for row in final_rows:
            output_writer.append_row(tab_name, {
                "event_name": row.event_name,
                "screen": row.screen,
                "telemetry_passed": row.telemetry_passed,
                "runtime_passed": row.runtime_passed,
                "overall_status": row.overall_status,
                "details": row.details,
                "timestamp": row.timestamp
            })

        logger.info(f"Audit results successfully written to tab '{tab_name}'.")
        return final_rows

if __name__ == "__main__":
    import os
    from core.output_writer import LocalExcelWriter
    
    print("Executing ValidationCombinerAgent self-test...")
    
    # 1. Mock Expected Events
    mock_events = [
        ExpectedEvent(event_name="login", screen="LoginScreen", user_action="Tap Login", raw_principle="", keywords=[]),
        ExpectedEvent(event_name="book_service", screen="ServiceScreen", user_action="Tap Book Now", raw_principle="", keywords=[])
    ]
    
    # 2. Mock Telemetry Validation Results
    mock_telemetry = [
        TelemetryValidationResult(event_name="login", passed=True, mismatched_keys=[], missing_keys=[], extra_keys=[]),
        TelemetryValidationResult(event_name="book_service", passed=False, mismatched_keys=["modelName"], missing_keys=[], extra_keys=[])
    ]
    
    # 3. Mock Runtime Validation Results
    mock_runtime = [
        RuntimeValidationResult(event_name="login", passed=True, expected_trigger="Tap Login", actual_trigger_observed=True, notes="Interaction succeeded"),
        RuntimeValidationResult(event_name="book_service", passed=True, expected_trigger="Tap Book Now", actual_trigger_observed=True, notes="Interaction succeeded")
    ]
    
    # 4. Run Combine and Write
    os.makedirs("./tmp", exist_ok=True)
    temp_writer = LocalExcelWriter("./tmp/test_combiner_results.xlsx")
    
    combiner = ValidationCombinerAgent()
    results = combiner.run(mock_events, mock_telemetry, mock_runtime, temp_writer)
    
    print("\nCombined Audit Rows:\n")
    for r in results:
        print(r.model_dump_json(indent=2))
        print("-" * 40)
        
    print("\nRead back rows from temporary sheet:")
    for row in temp_writer.read_all("FinalAudit"):
        print(row)
        
    if os.path.exists("./tmp/test_combiner_results.xlsx"):
        os.remove("./tmp/test_combiner_results.xlsx")
