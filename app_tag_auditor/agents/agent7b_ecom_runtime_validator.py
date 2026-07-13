import core.logger
from datetime import datetime
from core.models import ExpectedEcomEvent, CapturedEcomLog, EcomRuntimeValidationResult
from agents.agent1b_ecom_schema_reader import EcomSchemaReaderAgent

"""
EcomRuntimeValidatorAgent — runtime trigger validation for GA4 ecommerce events.

Checks ONLY:
  (1) not_implemented — event never fired (fire_count == 0)
  (2) double_fired    — event fired more than once on a single interaction

Wrong-place-firing and co-firing checks are intentionally excluded for ecom events:
  - Ecom events have no fixed screen (view_item can fire on any product page)
  - Co-firing is expected in ecom funnels (purchase legitimately co-fires with
    begin_checkout, add_shipping_info, add_payment_info in the same session)
"""

class EcomRuntimeValidatorAgent:
    def __init__(self):
        self.logger = core.logger.get_logger(__name__)

    def validate_event(self, event: ExpectedEcomEvent,
                      captured_logs: list[CapturedEcomLog]
                      ) -> EcomRuntimeValidationResult:
        fire_count = sum(1 for log in captured_logs if log.event_name == event.event_name)
        not_implemented = fire_count == 0
        double_fired = fire_count > 1

        if not_implemented:
            notes = "Event never fired — check implementation."
        elif double_fired:
            notes = f"Fired {fire_count} times on a single interaction; expected exactly once."
        else:
            notes = "OK."

        passed = (fire_count == 1)

        return EcomRuntimeValidationResult(
            event_name=event.event_name,
            passed=passed,
            fire_count=fire_count,
            not_implemented=not_implemented,
            double_fired=double_fired,
            notes=notes
        )

    def run(self, expected_events: list[ExpectedEcomEvent],
            captured_logs: list[CapturedEcomLog]
            ) -> list[EcomRuntimeValidationResult]:
        results = [self.validate_event(e, captured_logs) for e in expected_events]
        passed_count = sum(1 for r in results if r.passed)
        self.logger.info(
            f"Ecom runtime validation: {passed_count} passed, "
            f"{len(results) - passed_count} failed."
        )
        return results

if __name__ == "__main__":
    events = EcomSchemaReaderAgent().run()
    events_by_name = {e.event_name: e for e in events}

    shared_logs = [
        CapturedEcomLog(
            event_name="add_to_cart",
            top_level_params={"currency": "INR", "value": "149900.0"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        CapturedEcomLog(
            event_name="view_item",
            top_level_params={"currency": "INR", "value": "149900.0"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        CapturedEcomLog(
            event_name="view_item",
            top_level_params={"currency": "INR", "value": "149900.0"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
    ]

    test_cases = [
        ("add_to_cart", "PASS", "Fired once correctly"),
        ("view_item",   "FAIL", "Double fire — fired twice"),
        ("purchase",    "FAIL", "Not implemented — never fired"),
    ]

    validator = EcomRuntimeValidatorAgent()
    for event_name, expected, description in test_cases:
        event = events_by_name[event_name]
        result = validator.validate_event(event, shared_logs)
        actual = "PASS" if result.passed else "FAIL"
        label = "✅" if actual == expected else "❌"
        print(f"{label} {description} — Expected: {expected} | Got: {actual}")
        print(result.model_dump_json(indent=2))
        print("---")
