import os
import sys

# Add the project root to sys.path to allow execution from any directory
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.logger import get_logger
from core.models import ExpectedEcomEvent, CapturedEcomLog, EcomTelemetryValidationResult
import agents.agent1b_ecom_schema_reader

logger = get_logger(__name__)

class EcomTelemetryValidatorAgent:
    def __init__(self, schema_reader: agents.agent1b_ecom_schema_reader.EcomSchemaReaderAgent | None = None):
        self.schema_reader = schema_reader or agents.agent1b_ecom_schema_reader.EcomSchemaReaderAgent()
        self.schema_reader.load_config()

    def _validate_type(self, type_name: str, value) -> bool:
        type_lower = type_name.lower()
        if type_lower == "number":
            try:
                float(value)
                return True
            except (ValueError, TypeError):
                return False
        else:
            return str(value).strip() != ""

    def validate_event(self, event: ExpectedEcomEvent, captured_logs: list[CapturedEcomLog]) -> EcomTelemetryValidationResult:
        matching = [log for log in captured_logs if log.event_name == event.event_name]
        if not matching:
            logger.warning(f"No captured log for ecom event {event.event_name}")
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
        expected_event_names = set(event.event_param_names)
        captured_event_keys = set(log.top_level_params.keys())
        
        missing_event_keys = sorted(expected_event_names - captured_event_keys)
        extra_event_keys = sorted(captured_event_keys - expected_event_names)
        
        mismatched_event_keys = [
            name for name in event.event_param_names
            if name in captured_event_keys and not self._validate_type(
                self.schema_reader.get_param_type(name, is_item_param=False),
                log.top_level_params[name]
            )
        ]

        item_count_found = len(log.items)
        item_count_passed = item_count_found >= event.min_items
        required_item_names = set(event.required_item_param_names)
        known_item_pool = set(self.schema_reader._config["item_param_types"].keys())

        items_with_missing_keys = []
        items_with_type_errors = []
        items_with_custom_params = []
        items_with_discount_revenue_errors = []

        for idx, item in enumerate(log.items):
            item_keys = set(item.keys())
            missing = sorted(required_item_names - item_keys)
            if missing:
                items_with_missing_keys.append({"item_index": idx, "missing_keys": missing})

            type_errs = [
                k for k in item_keys
                if k in known_item_pool and not self._validate_type(
                    self.schema_reader.get_param_type(k, is_item_param=True),
                    item[k]
                )
            ]
            if type_errs:
                items_with_type_errors.append({"item_index": idx, "mismatched_keys": sorted(type_errs)})

            custom_keys = sorted(item_keys - known_item_pool)
            if custom_keys:
                items_with_custom_params.append({"item_index": idx, "custom_params": custom_keys})

            if "discount" in item_keys and "quantity" in item_keys:
                try:
                    discount = float(item["discount"])
                    quantity = float(item["quantity"])
                    if discount < 0 or quantity < 0:
                        items_with_discount_revenue_errors.append({
                            "item_index": idx,
                            "issue": "negative discount or quantity"
                        })
                except (ValueError, TypeError):
                    items_with_discount_revenue_errors.append({
                        "item_index": idx,
                        "issue": "discount/quantity not numeric, cannot verify discount amount"
                    })

            if "price" in item_keys and "quantity" in item_keys:
                try:
                    float(item["price"])
                    float(item["quantity"])
                except (ValueError, TypeError):
                    items_with_discount_revenue_errors.append({
                        "item_index": idx,
                        "issue": "price/quantity not numeric, cannot verify item revenue"
                    })

        passed = (
            (not missing_event_keys)
            and (not mismatched_event_keys)
            and item_count_passed
            and (not items_with_missing_keys)
            and (not items_with_type_errors)
            and (not items_with_discount_revenue_errors)
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

    def run(self, expected_events: list[ExpectedEcomEvent], captured_logs: list[CapturedEcomLog]) -> list[EcomTelemetryValidationResult]:
        logger.info(f"Running telemetry validation for {len(expected_events)} ecom events...")
        results = []
        for event in expected_events:
            res = self.validate_event(event, captured_logs)
            status = "PASS" if res.passed else "FAIL"
            logger.info(f"Event '{event.event_name}': {status}")
            results.append(res)
        return results

if __name__ == "__main__":
    reader = agents.agent1b_ecom_schema_reader.EcomSchemaReaderAgent()
    events = reader.run()
    
    # Map events by name for easy lookup
    events_map = {e.event_name: e for e in events}
    
    validator = EcomTelemetryValidatorAgent(reader)

    # a. add_to_cart — CORRECT -> expect PASS
    add_to_cart_event = events_map["add_to_cart"]
    log_a = CapturedEcomLog(
        event_name="add_to_cart",
        top_level_params={"currency": "INR", "value": 149900.0},
        items=[{
            "item_id": "SKU123",
            "item_name": "Himalayan 450",
            "price": 149900.0,
            "quantity": 1,
            "item_brand": "RoyalEnfield"
        }],
        timestamp="2026-06-30T12:00:00",
        source="logcat"
    )
    res_a = validator.validate_event(add_to_cart_event, [log_a])
    print("\nExpected: PASS")
    print(res_a.model_dump_json(indent=2))

    # b. view_item — CUSTOM ITEM PARAM -> expect PASS
    view_item_event = events_map["view_item"]
    log_b = CapturedEcomLog(
        event_name="view_item",
        top_level_params={"currency": "INR", "value": 149900.0},
        items=[{
            "item_id": "SKU123",
            "item_name": "Himalayan 450",
            "price": 149900.0,
            "quantity": 1,
            "engine_cc": "452"
        }],
        timestamp="2026-06-30T12:01:00",
        source="logcat"
    )
    res_b = validator.validate_event(view_item_event, [log_b])
    print("\nExpected: PASS (with items_with_custom_params listing engine_cc)")
    print(res_b.model_dump_json(indent=2))

    # c. purchase — MISSING REQUIRED ITEM FIELD -> expect FAIL
    purchase_event = events_map["purchase"]
    
    # Sub-case 1: missing required item field (price and quantity)
    log_c1 = CapturedEcomLog(
        event_name="purchase",
        top_level_params={
            "transaction_id": "T123",
            "value": 149900.0,
            "tax": 1000.0,
            "shipping": 500.0,
            "currency": "INR",
            "coupon": "PROMO",
            "customer_type": "new"
        },
        items=[{
            "item_id": "SKU123",
            "item_name": "Himalayan 450"
        }],
        timestamp="2026-06-30T12:02:00",
        source="logcat"
    )
    res_c1 = validator.validate_event(purchase_event, [log_c1])
    print("\nExpected: FAIL (missing required item fields)")
    print(res_c1.model_dump_json(indent=2))

    # Sub-case 2: empty items array -> expect FAIL
    log_c2 = CapturedEcomLog(
        event_name="purchase",
        top_level_params={
            "transaction_id": "T123",
            "value": 149900.0,
            "tax": 1000.0,
            "shipping": 500.0,
            "currency": "INR",
            "coupon": "PROMO",
            "customer_type": "new"
        },
        items=[],
        timestamp="2026-06-30T12:03:00",
        source="logcat"
    )
    res_c2 = validator.validate_event(purchase_event, [log_c2])
    print("\nExpected: FAIL (zero items)")
    print(res_c2.model_dump_json(indent=2))
