import os
import re
import json
from typing import Literal
from core.logger import get_logger
from core.models import ExpectedEvent, CrawlPlan, CrawlStep

logger = get_logger(__name__)

class CrawlPlannerAgent:
    """
    Agent3 CrawlPlannerAgent:
    Transforms expected events and sitemap configurations into sequential CrawlPlans
    with targeted UI tap selectors.
    """
    def __init__(self, navigation_map_path: str = "schemas/navigation_map.json", home_screen: str = "home"):
        self.navigation_map_path = navigation_map_path
        self.home_screen = home_screen
        self.navigation_map = self._load_navigation_map()

    def _load_navigation_map(self) -> dict:
        """Loads sitemap mapping from json file. Logs warning if missing."""
        path = self.navigation_map_path
        if not os.path.exists(path):
            possible_paths = [
                os.path.abspath(path),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
            ]
            path = next((p for p in possible_paths if os.path.exists(p)), path)

        if not os.path.exists(path):
            logger.warning(f"Navigation map file not found at: {self.navigation_map_path}. Empty map assumed.")
            return {}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse navigation map from {path}: {e}. Empty map assumed.")
            return {}

    def _build_navigation_steps(self, target_screen: str, current_screen: str) -> tuple[list[CrawlStep], bool]:
        """Looks up the target screen in sitemap and converts entries to CrawlSteps."""
        if current_screen == target_screen:
            return ([], True)

        if target_screen in self.navigation_map:
            raw_steps = self.navigation_map[target_screen]
            steps = []
            for order, step_dict in enumerate(raw_steps):
                steps.append(CrawlStep(
                    action_type=step_dict.get("action_type", "tap"),
                    target_selector=step_dict.get("target_selector", ""),
                    value=step_dict.get("value"),
                    step_order=order,
                    selector_strategy=step_dict.get("selector_strategy", "text")
                ))
            return (steps, True)

        return ([], False)

    def _is_passive_event(self, user_action: str) -> bool:
        """Determines if the event fires automatically without direct tap interaction."""
        ua = user_action.lower()
        passives = ["lands on", "navigates to", "opens", "views"]
        actives = ["click", "tap", "select"]
        has_passive = any(p in ua for p in passives)
        has_active = any(a in ua for a in actives)
        return has_passive and not has_active

    def _extract_tap_target(self, event: ExpectedEvent) -> tuple[str, str]:
        """Extracts the tap target selector and search strategy from event metadata."""
        # Hardcoded overrides for Royal Enfield application events to ensure stable resource-id lookups.
        event_lower = event.event_name.lower()
        if "add_motorcycle" in event_lower:
            return ("com.royalenfield.reprime:id/add_btn", "resource_id")
        elif "book_service" in event_lower:
            return ("com.royalenfield.reprime:id/book_now_layout", "resource_id")
        elif "view_service_history" in event_lower:
            return ("com.royalenfield.reprime:id/service_history_card_view", "resource_id")

        # 1. Check if click/CTA parameter text is defined
        target_param_names = {"clicktext", "buttontext", "label", "ctatext"}
        for param in event.expected_params:
            if param.param_name.lower() in target_param_names:
                if param.example_value:
                    return (param.example_value, "text")

        # 2. Match regex patterns inside the user_action description
        match = re.search(
            r'on (.+?)(?:\s+button\b|\s+in\b|\s+section\b|$)',
            event.user_action,
            re.IGNORECASE
        )
        if match:
            captured = match.group(1).strip()
            if captured:
                return (captured, "text")

        # 3. Warning/fallback: use event_name
        logger.warning(f"Low-confidence fallback tap selector for '{event.event_name}'")
        return (event.event_name, "content_desc")

    def build_plan(self, event: ExpectedEvent, current_screen: str = "home") -> CrawlPlan:
        """Constructs a complete CrawlPlan for an expected event."""
        nav_steps, resolved = self._build_navigation_steps(event.screen, current_screen)
        steps = list(nav_steps)
        
        if not self._is_passive_event(event.user_action):
            target_selector, strategy = self._extract_tap_target(event)
            steps.append(CrawlStep(
                action_type="tap",
                target_selector=target_selector,
                value=None,
                step_order=len(steps),
                selector_strategy=strategy
            ))

        return CrawlPlan(
            event_name=event.event_name,
            steps=steps,
            navigation_resolved=resolved
        )

    def run(self, expected_events: list[ExpectedEvent], current_screen: str = "home") -> list[CrawlPlan]:
        """Generates plans for all expected events and warns of unresolved navigation routes."""
        plans = []
        for event in expected_events:
            plan = self.build_plan(event, current_screen)
            if not plan.navigation_resolved:
                logger.warning(f"Navigation unresolved for target screen '{event.screen}' (event '{event.event_name}')")
            plans.append(plan)
        return plans

if __name__ == "__main__":
    from agents.agent1_schema_reader import SchemaReaderAgent

    print("Executing CrawlPlannerAgent self-test...")
    reader = SchemaReaderAgent()
    events = reader.run()

    planner = CrawlPlannerAgent()
    plans = planner.run(events, current_screen="home")

    print(f"\nSuccessfully generated {len(plans)} CrawlPlan objects:\n")
    for plan in plans:
        print(plan.model_dump_json(indent=2))
        print("-" * 40)
