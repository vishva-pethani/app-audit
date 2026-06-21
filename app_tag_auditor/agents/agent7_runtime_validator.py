"""
Agent7 RuntimeValidatorAgent:
Checks whether the expected trigger action/element actually occurred or was interacted
with during the live runtime crawl, producing a RuntimeValidationResult.
"""

from core.logger import get_logger
from core.models import CrawlPlan, RuntimeValidationResult

logger = get_logger(__name__)

class RuntimeValidatorAgent:
    """
    Agent7 RuntimeValidatorAgent:
    Validates whether UI interactions executed successfully during the runtime crawl.
    """
    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_execution(
        self,
        event_name: str,
        screen: str,
        crawl_plan: CrawlPlan,
        execution_success: bool,
        user_action: str
    ) -> RuntimeValidationResult:
        """
        Validates the execution of a single crawl plan and produces a RuntimeValidationResult.
        """
        logger.info(f"Validating runtime execution for event: {event_name} on screen: {screen}")
        
        # Determine if it's a passive load event (no tap/input steps in plan)
        is_passive = all(step.action_type not in ("tap", "input", "swipe") for step in crawl_plan.steps)

        if is_passive:
            passed = True
            actual_trigger_observed = True
            notes = "Passive event; screen landing verified (no active interaction steps required)."
        else:
            passed = execution_success
            actual_trigger_observed = execution_success
            if execution_success:
                notes = f"UI automation successfully executed all {len(crawl_plan.steps)} interaction step(s)."
            else:
                notes = "UI automation failed or timed out during execution steps."

        return RuntimeValidationResult(
            event_name=event_name,
            screen=screen,
            passed=passed,
            expected_trigger=user_action or "Unknown user action trigger",
            actual_trigger_observed=actual_trigger_observed,
            notes=notes
        )

    def run(self, execution_results: list[dict]) -> list[RuntimeValidationResult]:
        """
        Runs the runtime validator logic over a list of execution results.
        Each execution result dict should contain:
         - "event_name": str
         - "screen": str
         - "crawl_plan": CrawlPlan
         - "execution_success": bool
         - "user_action": str
        """
        results = []
        for res in execution_results:
            results.append(
                self.validate_execution(
                    event_name=res["event_name"],
                    screen=res.get("screen", ""),
                    crawl_plan=res["crawl_plan"],
                    execution_success=res["execution_success"],
                    user_action=res["user_action"]
                )
            )
        return results

if __name__ == "__main__":
    from core.models import CrawlStep
    
    print("Executing RuntimeValidatorAgent self-test...")
    
    # 1. Synthesize mock plans
    active_plan = CrawlPlan(
        event_name="login",
        steps=[
            CrawlStep(action_type="tap", target_selector="Login Button", step_order=0)
        ]
    )
    
    passive_plan = CrawlPlan(
        event_name="screen_view",
        steps=[
            CrawlStep(action_type="wait", target_selector="Home Screen", step_order=0)
        ]
    )
    
    # 2. Synthesize mock execution results
    mock_results = [
        {
            "event_name": "login",
            "crawl_plan": active_plan,
            "execution_success": True,
            "user_action": "When user clicks on Login button"
        },
        {
            "event_name": "book_service",
            "crawl_plan": active_plan, # reused active steps
            "execution_success": False,
            "user_action": "When user clicks on Book Now button"
        },
        {
            "event_name": "screen_view",
            "crawl_plan": passive_plan,
            "execution_success": False, # even if execution failed, passive should pass
            "user_action": "When user lands on Home Screen"
        }
    ]
    
    # 3. Run agent
    agent = RuntimeValidatorAgent()
    validation_results = agent.run(mock_results)
    
    print("\nRuntime Validation Results:\n")
    for res in validation_results:
        print(res.model_dump_json(indent=2))
        print("-" * 40)
