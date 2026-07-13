import core.logger
from datetime import datetime
from core.models import ExpectedEcomEvent, CapturedEcomLog, EcomTelemetryValidationResult
from agents.agent1b_ecom_schema_reader import EcomSchemaReaderAgent

class EcomTelemetryValidatorAgent:
    def __init__(self, schema_reader: EcomSchemaReaderAgent | None = None):
        self.schema_reader = schema_reader or EcomSchemaReaderAgent()
        self.schema_reader.load_config()
        self.logger = core.logger.get_logger(__name__)

    def _validate_type(self, type_name: str, value) -> bool:
        if value is None:
            return False
        t_name = type_name.lower()
        if t_name == "number":
            try:
                float(str(value))
                return True
            except (ValueError, TypeError):
                return False
        elif t_name == "boolean":
            if isinstance(value, bool):
                return True
            return str(value).lower() in ("true", "false", "0", "1")
        else:
            return str(value).strip() != ""

    def validate_event(self, event: ExpectedEcomEvent,
                      captured_logs: list[CapturedEcomLog]
                      ) -> EcomTelemetryValidationResult:
        matching = [log for log in captured_logs if log.event_name == event.event_name]
        if not matching:
            self.logger.warning(f"No captured log for '{event.event_name}'.")
            return EcomTelemetryValidationResult(
                event_name=event.event_name,
                passed=False,
                missing_event_keys=event.event_param_names,
                extra_event_keys=[],
                mismatched_event_keys=[],
                item_count_found=0,
                item_count_expected_min=event.min_items,
                item_count_passed=False,
                items_with_missing_keys=[],
                items_with_type_errors=[],
                items_with_custom_params=[],
                items_with_discount_revenue_errors=[]
            )

        log = matching[0]
        if len(matching) > 1:
            self.logger.info(
                f"Multiple captured logs for event '{event.event_name}'. "
                f"Only the first is validated."
            )

        expected_event_names = set(event.event_param_names)
        captured_event_keys = set(log.top_level_params.keys())

        missing_event_keys = sorted(expected_event_names - captured_event_keys)
        extra_event_keys = sorted(captured_event_keys - expected_event_names)

        mismatched_event_keys = []
        for param_name in event.event_param_names:
            if param_name in captured_event_keys:
                expected_type = self.schema_reader.get_param_type(param_name, is_item_param=False)
                actual_value = log.top_level_params[param_name]
                if not self._validate_type(expected_type, actual_value):
                    mismatched_event_keys.append(param_name)

        item_count_found = len(log.items)
        item_count_passed = item_count_found >= event.min_items

        known_item_pool = set(self.schema_reader._config["item_param_types"].keys())
        required_item_names = set(event.required_item_param_names)

        items_with_missing_keys = []
        items_with_type_errors = []
        items_with_custom_params = []
        items_with_discount_revenue_errors = []

        for idx, item in enumerate(log.items):
            item_keys = set(item.keys())

            # 4a. missing required keys
            missing = sorted(required_item_names - item_keys)
            if missing:
                items_with_missing_keys.append({"item_index": idx, "missing_keys": missing})

            # 4b. type errors for known params only
            type_errs = []
            for k in item_keys:
                if k in known_item_pool:
                    expected_type = self.schema_reader.get_param_type(k, is_item_param=True)
                    if not self._validate_type(expected_type, item[k]):
                        type_errs.append(k)
            if type_errs:
                items_with_type_errors.append({"item_index": idx, "mismatched_keys": sorted(type_errs)})

            # 4c. custom params - informational only
            custom_keys = sorted(item_keys - known_item_pool)
            if custom_keys:
                items_with_custom_params.append({"item_index": idx, "custom_params": custom_keys})

            # 4d. discount / revenue numeric sanity
            discount_revenue_issues = []
            if "discount" in item_keys and "quantity" in item_keys:
                try:
                    d = float(item["discount"])
                    q = float(item["quantity"])
                    if d < 0:
                        discount_revenue_issues.append("discount is negative")
                    if q < 0:
                        discount_revenue_issues.append("quantity is negative")
                except (ValueError, TypeError):
                    discount_revenue_issues.append("discount or quantity not numeric — cannot verify discount amount")

            if "price" in item_keys and "quantity" in item_keys:
                try:
                    float(item["price"])
                    float(item["quantity"])
                except (ValueError, TypeError):
                    if not any("not numeric" in issue for issue in discount_revenue_issues):
                        discount_revenue_issues.append("price or quantity not numeric — cannot verify item revenue")

            if discount_revenue_issues:
                items_with_discount_revenue_errors.append({"item_index": idx, "issues": discount_revenue_issues})

        passed = (
            not missing_event_keys and
            not mismatched_event_keys and
            item_count_passed and
            not items_with_missing_keys and
            not items_with_type_errors and
            not items_with_discount_revenue_errors
        )

        return EcomTelemetryValidationResult(
            event_name=event.event_name,
            passed=passed,
            missing_event_keys=missing_event_keys,
            extra_event_keys=extra_event_keys,
            mismatched_event_keys=mismatched_event_keys,
            item_count_found=item_count_found,
            item_count_expected_min=event.min_items,
            item_count_passed=item_count_passed,
            items_with_missing_keys=items_with_missing_keys,
            items_with_type_errors=items_with_type_errors,
            items_with_custom_params=items_with_custom_params,
            items_with_discount_revenue_errors=items_with_discount_revenue_errors
        )

    def run(self, expected_events: list[ExpectedEcomEvent],
            captured_logs: list[CapturedEcomLog]
            ) -> list[EcomTelemetryValidationResult]:
        results = [self.validate_event(e, captured_logs) for e in expected_events]
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        self.logger.info(f"Ecom telemetry validation: {passed_count} passed, {failed_count} failed.")
        return results

if __name__ == "__main__":
    reader = EcomSchemaReaderAgent()
    events = reader.run()
    events_by_name = {e.event_name: e for e in events}

    fixtures = [
        # CASE A - add_to_cart - CORRECT - expect PASS
        CapturedEcomLog(
            event_name="add_to_cart",
            top_level_params={"currency": "INR", "value": "149900.0"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1",
                    "item_brand": "RoyalEnfield", "engine_cc": "452"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        # CASE B - view_item - MISSING EVENT-LEVEL PARAM - expect FAIL
        CapturedEcomLog(
            event_name="view_item",
            top_level_params={"currency": "INR"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        # CASE C - purchase - ZERO ITEMS - expect FAIL
        CapturedEcomLog(
            event_name="purchase",
            top_level_params={"transaction_id": "T123", "value": "149900.0",
                              "tax": "0.0", "shipping": "0.0", "currency": "INR",
                              "coupon": "", "customer_type": "new"},
            items=[],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        # CASE D - begin_checkout - MISSING REQUIRED ITEM FIELD - expect FAIL
        CapturedEcomLog(
            event_name="begin_checkout",
            top_level_params={"currency": "INR", "value": "149900.0", "coupon": ""},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        # CASE E - view_cart - TYPE MISMATCH - expect FAIL
        CapturedEcomLog(
            event_name="view_cart",
            top_level_params={"currency": "INR", "value": "not_a_number"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
        # CASE F - add_to_cart - NEGATIVE DISCOUNT - expect FAIL
        CapturedEcomLog(
            event_name="add_to_cart",
            top_level_params={"currency": "INR", "value": "149900.0"},
            items=[{"item_id": "SKU123", "item_name": "Himalayan 450",
                    "price": "149900.0", "quantity": "1", "discount": "-100"}],
            timestamp=datetime.now().isoformat(), source="logcat"
        ),
    ]

    EXPECTED = ["PASS", "FAIL", "FAIL", "FAIL", "FAIL", "FAIL"]
    validator = EcomTelemetryValidatorAgent()

    for i, (fixture, expected) in enumerate(zip(fixtures, EXPECTED)):
        event = events_by_name[fixture.event_name]
        result = validator.validate_event(event, [fixture])
        actual = "PASS" if result.passed else "FAIL"
        label = "✅" if actual == expected else "❌"
        print(f"{label} Case {chr(65+i)} ({fixture.event_name}) — Expected: {expected} | Got: {actual}")
        print(result.model_dump_json(indent=2))
        print("---")
