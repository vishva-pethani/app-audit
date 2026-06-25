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

    def _normalize_name(self, name: str) -> str:
        """Normalizes a screen or event name to allow flexible matching."""
        s = re.sub(r'[\s_-]+', '', name.lower())
        if s.endswith("screen"):
            s = s[:-6]
        return s

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
                raw_map = json.load(f)
                return {self._normalize_name(k): v for k, v in raw_map.items()}
        except Exception as e:
            logger.warning(f"Failed to parse navigation map from {path}: {e}. Empty map assumed.")
            return {}

    # Keyword groups that map normalized screen-name fragments to common UI labels.
    # Used as a fallback when the screen is not in navigation_map.json.
    # Each entry: (set of screen-name keywords to match, list of UI tap candidates)
    # The first candidate that exists on screen will be tapped.
    _SCREEN_KEYWORD_NAV: list[tuple[set, list[dict]]] = [
        (
            {"account", "accounts", "login", "signin", "signup", "auth", "profile", "myaccount"},
            [
                {"target_selector": "Account", "selector_strategy": "text"},
                {"target_selector": "Accounts", "selector_strategy": "text"},
                {"target_selector": "My Account", "selector_strategy": "text"},
                {"target_selector": "Profile", "selector_strategy": "text"},
                {"target_selector": "Login", "selector_strategy": "text"},
                {"target_selector": "Sign In", "selector_strategy": "text"},
                {"target_selector": "Sign Up", "selector_strategy": "text"},
                {"target_selector": "account", "selector_strategy": "accessibility_id"},
                {"target_selector": "profile", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"cart", "bag", "basket", "checkout"},
            [
                {"target_selector": "Cart", "selector_strategy": "text"},
                {"target_selector": "Bag", "selector_strategy": "text"},
                {"target_selector": "Checkout", "selector_strategy": "text"},
                {"target_selector": "cart", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"wishlist", "wish", "saved", "favourite", "favorites"},
            [
                {"target_selector": "Wishlist", "selector_strategy": "text"},
                {"target_selector": "Saved", "selector_strategy": "text"},
                {"target_selector": "Favourites", "selector_strategy": "text"},
                {"target_selector": "wishlist", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"home", "main", "feed", "discover"},
            [
                {"target_selector": "Home", "selector_strategy": "text"},
                {"target_selector": "home", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"coupon", "offer", "promo", "discount", "voucher"},
            [
                {"target_selector": "Coupons", "selector_strategy": "text"},
                {"target_selector": "Offers", "selector_strategy": "text"},
                {"target_selector": "Promo", "selector_strategy": "text"},
                {"target_selector": "coupon", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"category", "categories", "browse", "shop", "store"},
            [
                {"target_selector": "Shop", "selector_strategy": "text"},
                {"target_selector": "Categories", "selector_strategy": "text"},
                {"target_selector": "Browse", "selector_strategy": "text"},
                {"target_selector": "Store", "selector_strategy": "text"},
                {"target_selector": "shop", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"order", "orders", "purchase", "history"},
            [
                {"target_selector": "Orders", "selector_strategy": "text"},
                {"target_selector": "My Orders", "selector_strategy": "text"},
                {"target_selector": "Purchase History", "selector_strategy": "text"},
                {"target_selector": "orders", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"search"},
            [
                {"target_selector": "Search", "selector_strategy": "text"},
                {"target_selector": "search", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"notification", "notifications", "alert", "alerts"},
            [
                {"target_selector": "Notifications", "selector_strategy": "text"},
                {"target_selector": "notifications", "selector_strategy": "accessibility_id"},
            ]
        ),
        (
            {"settings", "setting", "preference", "preferences"},
            [
                {"target_selector": "Settings", "selector_strategy": "text"},
                {"target_selector": "settings", "selector_strategy": "accessibility_id"},
            ]
        ),
    ]

    def _build_keyword_nav_steps(self, target_screen: str) -> list[CrawlStep]:
        """
        Generates heuristic navigation steps when the target screen is not in
        navigation_map.json.  Matches the normalised screen name against keyword
        groups and returns a list of CrawlStep candidates (the executor will try
        each selector strategy in order via its own fallback logic).
        Only the first matching group is used — multiple taps are avoided.
        """
        norm = self._normalize_name(target_screen)
        for keywords, candidates in self._SCREEN_KEYWORD_NAV:
            if any(kw in norm for kw in keywords):
                # Use the first candidate as a single nav step (best guess).
                # The executor's scroll+retry fallback will handle misses.
                best = candidates[0]
                logger.info(
                    f"Using keyword-based nav for '{target_screen}' → tap '{best['target_selector']}' "
                    f"via {best['selector_strategy']}"
                )
                return [CrawlStep(
                    action_type="tap",
                    target_selector=best["target_selector"],
                    value=None,
                    step_order=0,
                    selector_strategy=best["selector_strategy"]
                )]
        return []

    def _build_navigation_steps(self, target_screen: str, current_screen: str) -> tuple[list[CrawlStep], bool]:
        """Looks up the target screen in sitemap and converts entries to CrawlSteps."""
        norm_target = self._normalize_name(target_screen)
        norm_current = self._normalize_name(current_screen)

        if norm_current == norm_target:
            return ([], True)

        # Substring/prefix/suffix fallback matching
        matched_key = None
        if norm_target in self.navigation_map:
            matched_key = norm_target
        else:
            sorted_keys = sorted(self.navigation_map.keys(), key=len, reverse=True)
            for key in sorted_keys:
                if key in norm_target:
                    logger.info(f"Target screen '{target_screen}' not found exactly. Falling back to navigation steps of parent key '{key}'")
                    matched_key = key
                    break

        if matched_key:
            raw_steps = self.navigation_map[matched_key]
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
        passives = ["lands on", "navigates to", "opens", "views", "loads", "load", "shown", "appears", "launches", "launch"]
        actives = ["click", "tap", "select", "interact", "press"]
        has_passive = any(p in ua for p in passives)
        has_active = any(a in ua for a in actives)
        return has_passive and not has_active

    def _extract_tap_target(self, event: ExpectedEvent) -> tuple[str, str]:
        """Extracts the tap target selector and search strategy from event metadata."""
        event_lower = event.event_name.lower()
        ua_lower = event.user_action.lower()

        is_profile_trigger = (
            "profile" in event_lower or
            any(x in ua_lower for x in ["click on profile", "click profile", "tap on profile", "tap profile", "profile icon", "profile button", "click on avatar", "avatar icon"])
        )
        is_hamburger_trigger = (
            "hamburger" in event_lower or "moremenu" in event_lower or "more_menu" in event_lower or
            any(x in ua_lower for x in ["click on hamburger", "click hamburger", "tap on hamburger", "tap hamburger", "hamburger icon", "more menu", "side menu", "hamburger button"])
        )

        # Relative resource ID overrides (will be qualified with the active package name at runtime)
        if "add_motorcycle" in event_lower:
            return ("add_btn", "resource_id")
        elif "book_service" in event_lower:
            return ("book_now_layout", "resource_id")
        elif "view_service_history" in event_lower:
            return ("service_history_card_view", "resource_id")
        elif is_profile_trigger:
            return ("img_profile", "resource_id")
        elif is_hamburger_trigger:
            return ("img_moreMenu", "resource_id")

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
            if (captured.startswith('"') and captured.endswith('"')) or (captured.startswith("'") and captured.endswith("'")):
                captured = captured[1:-1].strip()
            if captured:
                return (captured, "text")

        # 3. Warning/fallback: use event_name only if it's non-empty and meaningful
        if event.event_name and event.event_name.strip():
            logger.warning(f"Low-confidence fallback tap selector for '{event.event_name}'")
            return (event.event_name, "content_desc")

        # 4. No usable selector found — return empty marker so build_plan can skip the tap
        logger.warning(f"No tap selector could be derived for event '{event.event_name}' — step will be skipped")
        return ("", "text")

    def build_plan(self, event: ExpectedEvent, current_screen: str = "home") -> CrawlPlan:
        """Constructs a complete CrawlPlan for an expected event."""
        nav_steps, resolved = self._build_navigation_steps(event.screen, current_screen)
        steps = list(nav_steps)
        
        if not self._is_passive_event(event.user_action):
            target_selector, strategy = self._extract_tap_target(event)
            # Only add the tap step if a usable selector was found
            if target_selector and target_selector.strip():
                steps.append(CrawlStep(
                    action_type="tap",
                    target_selector=target_selector,
                    value=None,
                    step_order=len(steps),
                    selector_strategy=strategy
                ))
            else:
                logger.warning(f"Skipping tap step for event '{event.event_name}' — no usable selector derived.")

        return CrawlPlan(
            event_name=event.event_name,
            screen=event.screen,
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
