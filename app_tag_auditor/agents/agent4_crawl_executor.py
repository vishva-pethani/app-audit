import os
import sys
import time
from typing import Literal
from core.logger import get_logger
from core.models import CrawlPlan, CrawlStep

logger = get_logger(__name__)

class CrawlExecutorAgent:
    """
    Agent4 CrawlExecutorAgent:
    Performs UI interactions on a connected Android device via Appium
    by executing sequentially sorted CrawlPlan steps.
    """
    def __init__(self, apk_path: str, appium_server_url: str | None = None, app_package: str | None = None):
        from core.config import get_settings
        settings = get_settings()
        
        self.apk_path = apk_path
        self.appium_server_url = appium_server_url or settings.APPIUM_SERVER_URL
        self.app_package = app_package or settings.ANDROID_APP_PACKAGE
        
        if not self.app_package:
            raise ValueError(
                "ANDROID_APP_PACKAGE must be defined in your .env file "
                "or passed explicitly to CrawlExecutorAgent."
            )
        self.driver = None

    def _build_driver(self):
        """Initializes the Appium WebDriver driver connection."""
        from appium import webdriver
        from appium.options.android.uiautomator2.UiAutomator2Options import UiAutomator2Options

        logger.info(f"Connecting to Appium server at {self.appium_server_url}...")
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.app = self.apk_path
        options.app_package = self.app_package
        options.automation_name = "UiAutomator2"
        options.no_reset = True
        options.auto_grant_permissions = True

        self.driver = webdriver.Remote(self.appium_server_url, options=options)
        logger.info("Appium driver successfully created and connected.")

    def _find_element_by_strategy(self, target_selector: str, strategy: str):
        """Finds elements using explicit waits and selector strategies."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        wait = WebDriverWait(self.driver, 10)

        if strategy == "text":
            xpath_exact = f'//*[@text="{target_selector}"]'
            try:
                return wait.until(EC.presence_of_element_located((AppiumBy.XPATH, xpath_exact)))
            except (TimeoutException, NoSuchElementException):
                xpath_contains = f'//*[contains(@text,"{target_selector}")]'
                try:
                    return wait.until(EC.presence_of_element_located((AppiumBy.XPATH, xpath_contains)))
                except (TimeoutException, NoSuchElementException):
                    raise NoSuchElementException(
                        f"Could not find element matching text '{target_selector}'"
                    )
        elif strategy == "resource_id":
            try:
                return wait.until(EC.presence_of_element_located((AppiumBy.ID, target_selector)))
            except TimeoutException:
                raise NoSuchElementException(f"Resource ID '{target_selector}' not found within 10s.")
        elif strategy in ("content_desc", "accessibility_id"):
            try:
                return wait.until(EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, target_selector)))
            except TimeoutException:
                raise NoSuchElementException(f"Accessibility ID '{target_selector}' not found within 10s.")
        else:
            raise ValueError(f"Unsupported selector strategy: {strategy}")

    def execute_step(self, step: CrawlStep) -> bool:
        """Executes a single step action on the device UI."""
        logger.info(f"Executing step {step.step_order}: {step.action_type} target={step.target_selector} strategy={step.selector_strategy}")
        try:
            if step.action_type == "tap":
                el = self._find_element_by_strategy(step.target_selector, step.selector_strategy)
                el.click()
            elif step.action_type == "input":
                el = self._find_element_by_strategy(step.target_selector, step.selector_strategy)
                el.clear()
                el.send_keys(step.value or "")
            elif step.action_type == "wait":
                time.sleep(2)
            elif step.action_type == "swipe":
                logger.warning("Generic vertical swipe triggered (non-targeted fallback).")
                size = self.driver.get_window_size()
                width = size['width']
                height = size['height']
                self.driver.swipe(
                    int(width * 0.5), int(height * 0.8),
                    int(width * 0.5), int(height * 0.2),
                    1000
                )
            elif step.action_type == "back":
                self.driver.back()
            else:
                logger.error(f"Unknown action type: {step.action_type}")
                return False
            return True
        except Exception as e:
            logger.error(f"Step {step.step_order} execution failed: {e}")
            return False

    def execute_plan(self, plan: CrawlPlan) -> bool:
        """Runs the complete ordered steps in a CrawlPlan."""
        if self.driver is None:
            self._build_driver()

        logger.info(f"Initiating CrawlPlan execution for event '{plan.event_name}'")
        sorted_steps = sorted(plan.steps, key=lambda s: s.step_order)

        for step in sorted_steps:
            success = self.execute_step(step)
            if not success:
                logger.error(f"Step {step.step_order} failed. Terminating CrawlPlan.")
                return False
            time.sleep(1)  # Allow UI to settle
            
        logger.info(f"CrawlPlan for event '{plan.event_name}' completed successfully.")
        return True

    def quit(self):
        """Safely tears down the Appium WebDriver driver session."""
        if self.driver is not None:
            logger.info("Closing Appium WebDriver session...")
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error closing driver session: {e}")
            self.driver = None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("=" * 60)
        print("Appium Crawl Executor Standalone Test Runner")
        print("=" * 60)
        print("Prerequisites Checklist:")
        print(" 1. Appium server must be running (normally at http://localhost:4723)")
        print(" 2. An Android device or emulator must be connected (run 'adb devices')")
        print(" 3. ANDROID_APP_PACKAGE must be configured in your app_tag_auditor/.env file")
        print("\nUsage:")
        print("  python -m agents.agent4_crawl_executor <path_to_apk>")
        print("=" * 60)
        sys.exit(0)

    apk = sys.argv[1]

    from agents.agent1_schema_reader import SchemaReaderAgent
    from agents.agent3_crawl_planner import CrawlPlannerAgent

    print("Loading expected events...")
    reader = SchemaReaderAgent()
    events = reader.run()

    print("Generating crawl plans...")
    planner = CrawlPlannerAgent()
    plans = planner.run(events, current_screen="home")

    if not plans:
        print("No crawl plans generated. Exiting.")
        sys.exit(0)

    # Take ONLY the first plan as a demo.
    # NOTE: Running multiple plans in sequence without resetting to a known screen
    # is a known follow-up - each plan currently assumes starting from "home".
    first_plan = plans[0]
    print(f"Executing first crawl plan for event '{first_plan.event_name}' as a demo:")
    print(first_plan.model_dump_json(indent=2))

    executor = None
    try:
        executor = CrawlExecutorAgent(apk_path=apk)
        success = executor.execute_plan(first_plan)
        print(f"\nDemo CrawlPlan execution result: {'SUCCESS' if success else 'FAILED'}")
    except Exception as e:
        print(f"\nExecution error occurred: {e}")
    finally:
        if executor:
            executor.quit()
