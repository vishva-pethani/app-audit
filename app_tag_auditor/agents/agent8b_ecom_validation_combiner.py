import json
from datetime import datetime
from typing import Literal
import core.logger
import core.config
import core.output_writer
from core.models import (
    ExpectedEcomEvent,
    EcomTelemetryValidationResult,
    EcomRuntimeValidationResult,
    FinalEcomAuditRow,
    CrawlPlan
)
from agents.agent1b_ecom_schema_reader import EcomSchemaReaderAgent

class EcomValidationCombinerAgent:
    def __init__(self):
        self.logger = core.logger.get_logger(__name__)

    def _build_details(self, telemetry: EcomTelemetryValidationResult,
                      runtime: EcomRuntimeValidationResult,
                      crawl_resolved: bool) -> str:
        clauses = []
        if not crawl_resolved:
            clauses.append("Crawl plan unresolved — event was not reached; result is inconclusive.")
        if runtime.not_implemented and crawl_resolved:
            clauses.append("Event never fired.")
        if runtime.double_fired:
            clauses.append(f"Fired {runtime.fire_count} times, expected exactly once.")
        if telemetry.missing_event_keys:
            clauses.append(f"Missing event params: {', '.join(telemetry.missing_event_keys)}.")
        if telemetry.extra_event_keys:
            clauses.append(f"Unexpected event params: {', '.join(telemetry.extra_event_keys)}.")
        if telemetry.mismatched_event_keys:
            clauses.append(f"Type/value errors in event params: {', '.join(telemetry.mismatched_event_keys)}.")
        if not telemetry.item_count_passed:
            clauses.append(f"Item count: expected >= {telemetry.item_count_expected_min}, found {telemetry.item_count_found}.")
        if telemetry.items_with_missing_keys:
            clauses.append(f"Items missing required keys: {json.dumps(telemetry.items_with_missing_keys)}.")
        if telemetry.items_with_type_errors:
            clauses.append(f"Items with type errors: {json.dumps(telemetry.items_with_type_errors)}.")
        if telemetry.items_with_custom_params:
            clauses.append(f"Custom item params (informational): {json.dumps(telemetry.items_with_custom_params)}.")
        if telemetry.items_with_discount_revenue_errors:
            clauses.append(f"Discount/revenue errors: {json.dumps(telemetry.items_with_discount_revenue_errors)}.")

        if not clauses:
            return "All checks passed."
        return " ".join(clauses)

    def _determine_overall_status(self,
                                  telemetry: EcomTelemetryValidationResult,
                                  runtime: EcomRuntimeValidationResult,
                                  crawl_resolved: bool
                                  ) -> Literal["PASS", "FAIL", "PARTIAL"]:
        if not crawl_resolved:
            return "PARTIAL"
        if telemetry.passed and runtime.passed:
            return "PASS"
        if not telemetry.passed and not runtime.passed:
            return "FAIL"
        return "PARTIAL"

    def combine_event(self,
                     event: ExpectedEcomEvent,
                     telemetry: EcomTelemetryValidationResult,
                     runtime: EcomRuntimeValidationResult,
                     crawl_resolved: bool
                     ) -> FinalEcomAuditRow:
        overall = self._determine_overall_status(telemetry, runtime, crawl_resolved)
        details = self._build_details(telemetry, runtime, crawl_resolved)
        return FinalEcomAuditRow(
            event_name=event.event_name,
            user_action=event.user_action,
            telemetry_passed=telemetry.passed,
            runtime_passed=runtime.passed,
            overall_status=overall,
            missing_event_keys=telemetry.missing_event_keys,
            extra_event_keys=telemetry.extra_event_keys,
            mismatched_event_keys=telemetry.mismatched_event_keys,
            item_count_found=telemetry.item_count_found,
            item_count_expected_min=telemetry.item_count_expected_min,
            item_count_passed=telemetry.item_count_passed,
            items_with_missing_keys=telemetry.items_with_missing_keys,
            items_with_type_errors=telemetry.items_with_type_errors,
            items_with_custom_params=telemetry.items_with_custom_params,
            items_with_discount_revenue_errors=telemetry.items_with_discount_revenue_errors,
            fire_count=runtime.fire_count,
            not_implemented=runtime.not_implemented,
            double_fired=runtime.double_fired,
            crawl_resolved=crawl_resolved,
            runtime_notes=runtime.notes,
            timestamp=datetime.now().isoformat()
        )

    def run(self,
           events: list[ExpectedEcomEvent],
           telemetry_results: list[EcomTelemetryValidationResult],
           runtime_results: list[EcomRuntimeValidationResult],
           crawl_plans: list[CrawlPlan]
           ) -> list[FinalEcomAuditRow]:
        telemetry_by_name = {r.event_name: r for r in telemetry_results}
        runtime_by_name = {r.event_name: r for r in runtime_results}
        plans_by_name = {p.event_name: p for p in crawl_plans}

        rows = []
        for event in events:
            telemetry = telemetry_by_name.get(event.event_name)
            runtime = runtime_by_name.get(event.event_name)
            plan = plans_by_name.get(event.event_name)
            if telemetry is None or runtime is None:
                self.logger.error(f"Missing telemetry or runtime result for '{event.event_name}' — skipping.")
                continue
            crawl_resolved = plan.navigation_resolved if plan is not None else False
            rows.append(self.combine_event(event, telemetry, runtime, crawl_resolved))

        pass_count = sum(1 for r in rows if r.overall_status == "PASS")
        partial_count = sum(1 for r in rows if r.overall_status == "PARTIAL")
        fail_count = sum(1 for r in rows if r.overall_status == "FAIL")
        self.logger.info(
            f"Ecom audit complete — PASS: {pass_count}, "
            f"PARTIAL: {partial_count}, FAIL: {fail_count}."
        )
        return rows

    def write_to_output(self, rows: list[FinalEcomAuditRow],
                       output_path: str | None = None) -> str:
        path = output_path or core.config.get_settings().ECOM_OUTPUT_PATH
        writer = core.output_writer.LocalExcelWriter(file_path=path)
        tab_name = "EcomAudit"
        headers = [
            "event_name", "user_action", "telemetry_passed", "runtime_passed",
            "overall_status", "missing_event_keys", "extra_event_keys",
            "mismatched_event_keys", "item_count_found", "item_count_expected_min",
            "item_count_passed", "items_with_missing_keys", "items_with_type_errors",
            "items_with_custom_params", "items_with_discount_revenue_errors",
            "fire_count", "not_implemented", "double_fired", "crawl_resolved",
            "runtime_notes", "timestamp"
        ]
        writer.ensure_headers(tab_name, headers)
        for row in rows:
            raw = row.model_dump()
            for key in ["missing_event_keys", "extra_event_keys",
                        "mismatched_event_keys", "items_with_missing_keys",
                        "items_with_type_errors", "items_with_custom_params",
                        "items_with_discount_revenue_errors"]:
                raw[key] = json.dumps(raw[key])
            writer.append_row(tab_name, raw)
        self.logger.info(f"Ecom audit results written to {path}")
        return path

if __name__ == "__main__":
    events = EcomSchemaReaderAgent().run()
    events_by_name = {e.event_name: e for e in events}

    def make_telemetry(event_name, passed, **overrides):
        defaults = dict(
            event_name=event_name, passed=passed,
            missing_event_keys=[], extra_event_keys=[], mismatched_event_keys=[],
            item_count_found=1, item_count_expected_min=1, item_count_passed=True,
            items_with_missing_keys=[], items_with_type_errors=[],
            items_with_custom_params=[], items_with_discount_revenue_errors=[]
        )
        defaults.update(overrides)
        return EcomTelemetryValidationResult(**defaults)

    def make_runtime(event_name, fire_count):
        not_impl = fire_count == 0
        doubled = fire_count > 1
        notes = ("OK." if fire_count == 1 else
                 "Event never fired — check implementation." if not_impl else
                 f"Fired {fire_count} times on a single interaction; expected exactly once.")
        return EcomRuntimeValidationResult(
            event_name=event_name, passed=(fire_count == 1),
            fire_count=fire_count, not_implemented=not_impl,
            double_fired=doubled, notes=notes
        )

    test_cases = [
        ("add_to_cart", make_telemetry("add_to_cart", True), make_runtime("add_to_cart", 1), True, "PASS"),
        ("view_item", make_telemetry("view_item", True), make_runtime("view_item", 2), True, "PARTIAL"),
        ("purchase", make_telemetry("purchase", False, missing_event_keys=["transaction_id"], item_count_found=0, item_count_passed=False), make_runtime("purchase", 0), True, "FAIL"),
        ("begin_checkout", make_telemetry("begin_checkout", False, items_with_missing_keys=[{"item_index":0, "missing_keys":["price"]}]), make_runtime("begin_checkout", 1), True, "PARTIAL"),
        ("view_cart", make_telemetry("view_cart", True), make_runtime("view_cart", 1), False, "PARTIAL"),
    ]

    combiner = EcomValidationCombinerAgent()
    rows = []
    for event_name, telemetry, runtime, crawl_resolved, expected in test_cases:
        event = events_by_name[event_name]
        row = combiner.combine_event(event, telemetry, runtime, crawl_resolved)
        rows.append(row)
        actual = row.overall_status
        label = "✅" if actual == expected else "❌"
        print(f"{label} {event_name} — Expected: {expected} | Got: {actual}")
        print(row.model_dump_json(indent=2))
        print("---")

    import tempfile, os
    tmp_path = os.path.join(tempfile.mkdtemp(), "ecom_test_output.xlsx")
    written_path = combiner.write_to_output(rows, output_path=tmp_path)
    reader = core.output_writer.LocalExcelWriter(file_path=written_path)
    read_back = reader.read_all("EcomAudit")
    print(f"\nExcel round-trip: wrote {len(rows)} rows, read back {len(read_back)} rows.")
    print(f"Columns: {list(read_back[0].keys()) if read_back else 'N/A'}")
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    print("Temp file cleaned up.")
