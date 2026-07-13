import os
import json
import core.logger
import agents.agent1b_ecom_schema_reader
from core.models import ExpectedEcomEvent, CrawlPlan, CrawlStep

KNOWN_ECOM_EVENTS = frozenset([
    "view_item_list", "select_item", "view_item", "add_to_cart",
    "add_to_wishlist", "view_cart", "remove_from_cart", "begin_checkout",
    "add_shipping_info", "add_payment_info", "purchase", "refund",
    "view_promotion", "select_promotion"
])

class EcomCrawlPlannerAgent:
    """
    Reads schemas/ecom_crawl_map.json and builds a CrawlPlan per ecom event.
    Events with FILL_IN_* selectors are skipped (navigation_resolved=False).
    refund is always resolved with empty steps (server-side event).
    """
    def __init__(self, crawl_map_path: str = "schemas/ecom_crawl_map.json"):
        self.crawl_map_path = crawl_map_path
        self._crawl_map = None
        self.logger = core.logger.get_logger(__name__)

    def _load_crawl_map(self) -> dict:
        if self._crawl_map is not None:
            return self._crawl_map

        path = self.crawl_map_path
        if not os.path.exists(path):
            possible_paths = [
                os.path.abspath(path),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
            ]
            path = next((p for p in possible_paths if os.path.exists(p)), path)

        if not os.path.exists(path):
            self.logger.warning(
                f"ecom_crawl_map.json not found at {self.crawl_map_path} — "
                f"all plans will be unresolved. Create the file and fill in selectors."
            )
            self._crawl_map = {}
            return {}

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if "_instructions" in data:
            data.pop("_instructions")

        filtered_map = {}
        for k, v in data.items():
            if k not in KNOWN_ECOM_EVENTS:
                self.logger.warning(f"Unknown ecom event '{k}' in ecom_crawl_map.json — ignoring.")
            else:
                filtered_map[k] = v

        self._crawl_map = filtered_map
        return self._crawl_map

    def _has_placeholders(self, steps: list[dict]) -> bool:
        for s in steps:
            sel = s.get("target_selector")
            if isinstance(sel, str) and "FILL_IN" in sel.upper():
                return True
        return False

    def build_plan(self, event: ExpectedEcomEvent) -> CrawlPlan:
        crawl_map = self._load_crawl_map()
        steps_raw = crawl_map.get(event.event_name, None)

        if event.event_name == "refund" and steps_raw == []:
            self.logger.info("refund is server-side — no crawl steps needed, marking resolved.")
            return CrawlPlan(event_name=event.event_name, steps=[], navigation_resolved=True)

        if steps_raw is None:
            self.logger.warning(
                f"No entry for '{event.event_name}' in ecom_crawl_map.json "
                f"— add it and fill in selectors."
            )
            return CrawlPlan(event_name=event.event_name, steps=[], navigation_resolved=False)

        if not steps_raw:
            self.logger.warning(
                f"Empty steps for '{event.event_name}' in ecom_crawl_map.json "
                f"— add steps or this event will be skipped."
            )
            return CrawlPlan(event_name=event.event_name, steps=[], navigation_resolved=False)

        if self._has_placeholders(steps_raw):
            self.logger.warning(
                f"'{event.event_name}' still has FILL_IN placeholder selectors "
                f"— fill in ecom_crawl_map.json before running."
            )
            return CrawlPlan(event_name=event.event_name, steps=[], navigation_resolved=False)

        sorted_steps_raw = sorted(steps_raw, key=lambda x: x.get("step_order", 0))
        steps = []
        for s in sorted_steps_raw:
            action_type = s.get("action_type")
            step_order = s.get("step_order", 0)
            if action_type not in ("tap", "input", "swipe", "wait", "back"):
                self.logger.warning(
                    f"Invalid action_type '{action_type}' for event '{event.event_name}' "
                    f"step {step_order} — skipping this step."
                )
                continue
            
            steps.append(CrawlStep(
                action_type=action_type,
                target_selector=s.get("target_selector", ""),
                value=s.get("value"),
                step_order=step_order,
                selector_strategy=s.get("selector_strategy", "text")
            ))

        return CrawlPlan(event_name=event.event_name, steps=steps, navigation_resolved=True)

    def run(self, expected_events: list[ExpectedEcomEvent]) -> list[CrawlPlan]:
        plans = [self.build_plan(e) for e in expected_events]
        resolved = [p for p in plans if p.navigation_resolved]
        skipped = [p for p in plans if not p.navigation_resolved]
        self.logger.info(f"Ecom crawl plans: {len(resolved)} resolved, {len(skipped)} skipped.")
        return plans

if __name__ == "__main__":
    reader = agents.agent1b_ecom_schema_reader.EcomSchemaReaderAgent()
    events = reader.run()
    planner = EcomCrawlPlannerAgent()
    plans = planner.run(events)

    for idx, p in enumerate(plans):
        print(p.model_dump_json(indent=2))
        if idx < len(plans) - 1:
            print("---")
            
    resolved_count = sum(1 for p in plans if p.navigation_resolved)
    skipped_count = sum(1 for p in plans if not p.navigation_resolved)
    print(
        f"Summary — Resolved: {resolved_count} | Skipped: {skipped_count} | "
        f"Intentionally empty (refund): 1"
    )
