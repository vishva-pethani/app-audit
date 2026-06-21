"""
Agent6 TelemetryValidatorAgent:
Compares the captured logs (CapturedLog.raw_params) against the expected parameters
defined in the schema (ExpectedEvent.expected_params) and produces a TelemetryValidationResult.
"""

from typing import Any
from core.logger import get_logger
from core.models import ExpectedEvent, CapturedLog, TelemetryValidationResult

logger = get_logger(__name__)

class TelemetryValidatorAgent:
    """
    Agent6 TelemetryValidatorAgent:
    Validates Firebase telemetry log parameters against expected schemas.
    """
    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_event(self, event: ExpectedEvent, logs: list[CapturedLog]) -> TelemetryValidationResult:
        """
        Compares all captured logs for a specific event against the expected schema
        and returns the best validation result (matching log with the fewest errors).
        """
        matching_logs = [log for log in logs if log.event_name == event.event_name]
        
        if not matching_logs:
            logger.warning(f"No captured logs found for event: {event.event_name}")
            return TelemetryValidationResult(
                event_name=event.event_name,
                screen=event.screen,
                passed=False,
                missing_keys=[p.param_name for p in event.expected_params],
                mismatched_keys=[],
                extra_keys=[]
            )

        best_result = None
        best_error_score = float('inf')

        # Evaluate all matching logs to find the one that best fits the schema
        for log in matching_logs:
            expected_keys = {p.param_name for p in event.expected_params}
            actual_keys = set(log.raw_params.keys())

            missing_keys = list(expected_keys - actual_keys)
            extra_keys = list(actual_keys - expected_keys)
            mismatched_keys = []

            for param in event.expected_params:
                name = param.param_name
                if name in log.raw_params:
                    actual_val = str(log.raw_params[name]).strip()
                    expected_val = str(param.example_value).strip()
                    # Check value mismatch if expected example value is defined in the schema
                    if expected_val and actual_val != expected_val:
                        mismatched_keys.append(name)

            passed = (len(missing_keys) == 0 and len(mismatched_keys) == 0)
            error_score = len(missing_keys) + len(mismatched_keys)

            result = TelemetryValidationResult(
                event_name=event.event_name,
                screen=event.screen,
                passed=passed,
                mismatched_keys=mismatched_keys,
                missing_keys=missing_keys,
                extra_keys=extra_keys,
                matched_log=log
            )

            # If we find a fully passing log, we can return it immediately
            if passed:
                return result

            # Otherwise, keep track of the log with the lowest error score
            if error_score < best_error_score:
                best_error_score = error_score
                best_result = result

        return best_result

    def run(self, expected_events: list[ExpectedEvent], logs: list[CapturedLog]) -> list[TelemetryValidationResult]:
        """Runs the validation logic across all expected events."""
        logger.info(f"Running telemetry validation for {len(expected_events)} events...")
        results = []
        for event in expected_events:
            results.append(self.validate_event(event, logs))
        return results

if __name__ == "__main__":
    from agents.agent1_schema_reader import SchemaReaderAgent

    print("Executing TelemetryValidatorAgent self-test...")
    
    # 1. Load schema expected events
    reader = SchemaReaderAgent()
    expected_events = reader.run()

    # 2. Synthesize captured logs
    sample_logs = [
        CapturedLog(
            event_name="screen_view",
            raw_params={"screenname": "My_RE_screen", "extra_param": "dummy"},
            timestamp="2026-06-21T10:00:00",
            source="logcat"
        ),
        CapturedLog(
            # Missing parameter: screenname
            event_name="add_motorcycle",
            raw_params={},
            timestamp="2026-06-21T10:01:00",
            source="logcat"
        ),
        CapturedLog(
            # Value mismatch on modelName
            event_name="book_service",
            raw_params={
                "clickText": "Book Now",
                "modelName": "Himalayan 450", # expected: Super Meteor 650
                "sectionHeading": "Service Booking",
                "screenname": "My_RE_screen"
            },
            timestamp="2026-06-21T10:02:00",
            source="logcat"
        ),
        CapturedLog(
            # Perfect match
            event_name="view_service_history",
            raw_params={
                "clickText": "My Service History",
                "modelName": "Himalayan 450",
                "screenname": "My_RE_screen"
            },
            timestamp="2026-06-21T10:03:00",
            source="logcat"
        )
    ]

    # 3. Run validation
    validator = TelemetryValidatorAgent()
    validation_results = validator.run(expected_events, sample_logs)

    print("\nValidation Results:\n")
    for res in validation_results:
        print(res.model_dump_json(indent=2))
        print("-" * 40)
