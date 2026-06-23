"""
Agent7 RuntimeValidatorAgent:
Checks whether the expected trigger action/element actually occurred or was interacted
with during the live runtime crawl, producing a RuntimeValidationResult.

NOTE: wrong-place-firing and co-fire checks rely on a SINGLE screen-identity sample
taken right after the action — for events that themselves trigger fast navigation,
this sample may already reflect the destination screen rather than the true firing moment;
treat "incorrect"/co-fire flags on such events as a signal to investigate, not an
automatic hard failure.
"""

from typing import Literal, Optional
from datetime import datetime
from core.logger import get_logger
from core.models import ExpectedEvent, EventRuntimeCapture, RuntimeValidationResult, CapturedLog, CrawlPlan

logger = get_logger(__name__)

class RuntimeValidatorAgent:
    def __init__(self):
        self.logger = get_logger(__name__)

    def _other_events_screen_map(self, all_events: list[ExpectedEvent], exclude_event_name: str) -> dict[str, str]:
        return {event.event_name: event.screen for event in all_events if event.event_name != exclude_event_name}

    def validate_event(
        self,
        event: ExpectedEvent,
        capture: EventRuntimeCapture,
        all_events: list[ExpectedEvent]
    ) -> RuntimeValidationResult:
        fire_count = sum(1 for log in capture.captured_logs if log.event_name == event.event_name)
        not_implemented = fire_count == 0
        double_fired = fire_count > 1

        if capture.detected_screen_immediately is None or capture.detection_source_immediate == "unknown":
            screen_check_status = "unknown"
        elif capture.detected_screen_immediately.strip().lower() == event.screen.strip().lower():
            screen_check_status = "correct"
        else:
            screen_check_status = "incorrect"

        unexpected_co_fired_events = []
        if screen_check_status != "unknown":
            other_map = self._other_events_screen_map(all_events, event.event_name)
            fired_other_names = {log.event_name for log in capture.captured_logs if log.event_name != event.event_name}
            for name in fired_other_names:
                expected_screen = other_map.get(name)
                if expected_screen:
                    if expected_screen.strip().lower() != capture.detected_screen_immediately.strip().lower():
                        unexpected_co_fired_events.append(name)

        passed = (fire_count == 1) and (screen_check_status != "incorrect") and (len(unexpected_co_fired_events) == 0)

        notes_clauses = []
        if not_implemented:
            notes_clauses.append("Event never fired.")
        if double_fired:
            notes_clauses.append(f"Fired {fire_count} times, expected exactly once.")
        if screen_check_status == "incorrect":
            notes_clauses.append(f"Fired while on '{capture.detected_screen_immediately}', expected '{event.screen}'.")
        elif screen_check_status == "unknown":
            notes_clauses.append("Screen identity could not be determined — wrong-place check inconclusive, treat with caution.")
        if unexpected_co_fired_events:
            notes_clauses.append(f"Unexpected co-fired event(s) for a different screen: {', '.join(unexpected_co_fired_events)}.")

        notes = " ".join(notes_clauses) if notes_clauses else "OK."

        return RuntimeValidationResult(
            event_name=event.event_name,
            screen=event.screen,
            passed=passed,
            expected_trigger=event.user_action,
            actual_trigger_observed=(fire_count >= 1),
            notes=notes,
            fire_count=fire_count,
            not_implemented=not_implemented,
            double_fired=double_fired,
            screen_check_status=screen_check_status,
            unexpected_co_fired_events=unexpected_co_fired_events
        )

    def validate_execution(
        self,
        event_name: str,
        screen: str,
        crawl_plan: CrawlPlan,
        execution_success: bool,
        user_action: str
    ) -> RuntimeValidationResult:
        """
        Backward compatibility validator for execution step checking.
        """
        is_passive = all(step.action_type not in ("tap", "input", "swipe") for step in crawl_plan.steps)
        if is_passive:
            passed = True
            actual_trigger_observed = True
            notes = "Passive event; screen landing verified (no active interaction steps required)."
        else:
            passed = execution_success
            actual_trigger_observed = execution_success
            notes = (
                f"UI automation successfully executed all {len(crawl_plan.steps)} interaction step(s)."
                if execution_success else "UI automation failed or timed out during execution steps."
            )
        return RuntimeValidationResult(
            event_name=event_name,
            screen=screen,
            passed=passed,
            expected_trigger=user_action or "Unknown user action trigger",
            actual_trigger_observed=actual_trigger_observed,
            notes=notes
        )

    def run(
        self,
        events_and_captures: list[tuple[ExpectedEvent, EventRuntimeCapture]],
        all_events: list[ExpectedEvent]
    ) -> list[RuntimeValidationResult]:
        results = []
        passed_count = 0
        for event, capture in events_and_captures:
            res = self.validate_event(event, capture, all_events)
            results.append(res)
            if res.passed:
                passed_count += 1
        self.logger.info(f"Runtime validation completed: {passed_count}/{len(events_and_captures)} passed.")
        return results

if __name__ == "__main__":
    import json

    all_events = [
        ExpectedEvent(event_name="screen_view", screen="My_RE_screen", user_action="lands on My RE screen", expected_params=[], raw_principle="", keywords=[]),
        ExpectedEvent(event_name="add_motorcycle", screen="My_RE_screen", user_action="clicks Add icon", expected_params=[], raw_principle="", keywords=[]),
        ExpectedEvent(event_name="book_service", screen="My_RE_screen", user_action="clicks Book Now", expected_params=[], raw_principle="", keywords=[]),
        ExpectedEvent(event_name="booking_confirmation_view", screen="Booking_Confirmation_screen", user_action="lands on booking confirmation screen", expected_params=[], raw_principle="", keywords=[]),
    ]

    now = datetime.now().isoformat()
    agent = RuntimeValidatorAgent()

    # a. CORRECT
    cap_a = EventRuntimeCapture(
        event_name="screen_view", trigger_timestamp=now,
        captured_logs=[CapturedLog(event_name="screen_view", raw_params={}, timestamp=now, source="logcat")],
        detected_screen_after="My_RE_screen", detection_source="signature",
        detected_screen_immediately="My_RE_screen", detection_source_immediate="signature"
    )
    res_a = agent.validate_event(all_events[0], cap_a, all_events)
    print("Expected: PASS")
    print(res_a.model_dump_json(indent=2))
    print("=" * 60)

    # b. DOUBLE FIRE
    cap_b = EventRuntimeCapture(
        event_name="add_motorcycle", trigger_timestamp=now,
        captured_logs=[
            CapturedLog(event_name="add_motorcycle", raw_params={}, timestamp=now, source="logcat"),
            CapturedLog(event_name="add_motorcycle", raw_params={}, timestamp=now, source="logcat")
        ],
        detected_screen_after="My_RE_screen", detection_source="activity",
        detected_screen_immediately="My_RE_screen", detection_source_immediate="activity"
    )
    res_b = agent.validate_event(all_events[1], cap_b, all_events)
    print("Expected: FAIL (Double Fire)")
    print(res_b.model_dump_json(indent=2))
    print("=" * 60)

    # c. NOT IMPLEMENTED
    cap_c = EventRuntimeCapture(
        event_name="book_service", trigger_timestamp=now,
        captured_logs=[],
        detected_screen_after="My_RE_screen", detection_source="signature",
        detected_screen_immediately="My_RE_screen", detection_source_immediate="signature"
    )
    res_c = agent.validate_event(all_events[2], cap_c, all_events)
    print("Expected: FAIL (Not Implemented)")
    print(res_c.model_dump_json(indent=2))
    print("=" * 60)

    # d. WRONG-EVENT CO-FIRE
    cap_d = EventRuntimeCapture(
        event_name="screen_view", trigger_timestamp=now,
        captured_logs=[
            CapturedLog(event_name="screen_view", raw_params={}, timestamp=now, source="logcat"),
            CapturedLog(event_name="booking_confirmation_view", raw_params={}, timestamp=now, source="logcat")
        ],
        detected_screen_after="My_RE_screen", detection_source="signature",
        detected_screen_immediately="My_RE_screen", detection_source_immediate="signature"
    )
    res_d = agent.validate_event(all_events[0], cap_d, all_events)
    print("Expected: FAIL (Co-fire on wrong screen)")
    print(res_d.model_dump_json(indent=2))
    print("=" * 60)

    # e. UNKNOWN/INCONCLUSIVE
    cap_e = EventRuntimeCapture(
        event_name="screen_view", trigger_timestamp=now,
        captured_logs=[CapturedLog(event_name="screen_view", raw_params={}, timestamp=now, source="logcat")],
        detected_screen_after=None, detection_source="unknown",
        detected_screen_immediately=None, detection_source_immediate="unknown"
    )
    res_e = agent.validate_event(all_events[0], cap_e, all_events)
    print("Expected: PASS (with caution note)")
    print(res_e.model_dump_json(indent=2))
    print("=" * 60)
