import os
import sys
import time
import re
from core.logger import get_logger
from core.models import CrawlPlan, CrawlStep
from core.config import get_settings

logger = get_logger(__name__)

class CrawlExecutorAgent:
    """
    Agent4 CrawlExecutorAgent:
    Performs UI interactions on a connected Android device via Appium
    by executing sequentially sorted CrawlPlan steps.
    """
    def __init__(self, apk_path: str, appium_server_url: str | None = None, app_package: str | None = None):
        settings = get_settings()
        self.apk_path = apk_path
        self.appium_server_url = appium_server_url or settings.APPIUM_SERVER_URL
        self.app_package = app_package or settings.ANDROID_APP_PACKAGE
        
        if not self.app_package and apk_path and os.path.exists(apk_path):
            self.app_package = self._extract_package_name(apk_path)
            
        if not self.app_package:
            raise ValueError(
                "ANDROID_APP_PACKAGE must be defined in your .env file, "
                "passed explicitly to CrawlExecutorAgent, or extractable from a valid APK."
            )
        self.driver = None

    def _extract_package_name(self, apk_path: str) -> str | None:
        """Attempts to dynamically extract the Android package name from the APK file."""
        import shutil, subprocess, hashlib
        aapt = shutil.which("aapt")
        if not aapt:
            android_home = os.environ.get("ANDROID_HOME") or "/home/vishvapethani/Android/Sdk"
            build_tools = os.path.join(android_home, "build-tools") if android_home else ""
            if os.path.exists(build_tools):
                for v in sorted(os.listdir(build_tools), reverse=True):
                    cand = os.path.join(build_tools, v, "aapt")
                    if os.path.exists(cand):
                        aapt = cand
                        break
        if aapt:
            try:
                res = subprocess.run([aapt, "dump", "badging", apk_path], capture_output=True, text=True, check=True)
                match = re.search(r"package:\s+name='([^']+)'", res.stdout)
                if match:
                    logger.info(f"Dynamically extracted package: '{match.group(1)}'")
                    return match.group(1)
            except Exception:
                pass
        try:
            h = hashlib.sha1()
            with open(apk_path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            cache_key = h.hexdigest()
            paths = [
                os.path.join(get_settings().TEMP_STORAGE_DIR, "decompiled", cache_key, "resources", "AndroidManifest.xml"),
                os.path.join(get_settings().TEMP_STORAGE_DIR, "decompiled", cache_key, "AndroidManifest.xml")
            ]
            for path in paths:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    match = re.search(r'package="([^"]+)"', content)
                    if match:
                        logger.info(f"Extracted package from manifest: '{match.group(1)}'")
                        return match.group(1)
        except Exception:
            pass
        return None

    def _build_driver(self):
        """Initializes the Appium WebDriver driver connection."""
        from appium import webdriver
        from appium.options.android.uiautomator2.UiAutomator2Options import UiAutomator2Options
        logger.info(f"Connecting to Appium at {self.appium_server_url} for package {self.app_package}...")
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
        try:
            if strategy == "text":
                try:
                    return wait.until(EC.presence_of_element_located((AppiumBy.XPATH, f'//*[@text="{target_selector}"]')))
                except (TimeoutException, NoSuchElementException):
                    return wait.until(EC.presence_of_element_located((AppiumBy.XPATH, f'//*[contains(@text,"{target_selector}")]')))
            elif strategy == "resource_id":
                return wait.until(EC.presence_of_element_located((AppiumBy.ID, target_selector)))
            elif strategy in ("content_desc", "accessibility_id"):
                return wait.until(EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, target_selector)))
            raise ValueError(f"Unsupported selector strategy: {strategy}")
        except TimeoutException:
            raise NoSuchElementException(f"Element '{target_selector}' not found under {strategy} within 10s.")

    def execute_step(self, step: CrawlStep) -> bool:
        """Executes a single step action on the device UI."""
        logger.info(f"Step {step.step_order}: {step.action_type} target={step.target_selector}")
        try:
            if step.action_type == "tap":
                self._find_element_by_strategy(step.target_selector, step.selector_strategy).click()
            elif step.action_type == "input":
                el = self._find_element_by_strategy(step.target_selector, step.selector_strategy)
                el.clear()
                el.send_keys(step.value or "")
            elif step.action_type == "wait":
                time.sleep(2)
            elif step.action_type == "swipe":
                size = self.driver.get_window_size()
                w, h = size['width'], size['height']
                self.driver.swipe(int(w * 0.5), int(h * 0.8), int(w * 0.5), int(h * 0.2), 1000)
            elif step.action_type == "back":
                self.driver.back()
            else:
                return False
            return True
        except Exception as e:
            logger.error(f"Step {step.step_order} failed: {e}")
            return False

    def execute_plan(self, plan: CrawlPlan) -> bool:
        """Runs the complete ordered steps in a CrawlPlan."""
        if self.driver is None:
            self._build_driver()
        logger.info(f"Executing CrawlPlan for event '{plan.event_name}'")
        for step in sorted(plan.steps, key=lambda s: s.step_order):
            if not self.execute_step(step):
                return False
            time.sleep(1)
        return True

    def quit(self):
        """Safely tears down the Appium WebDriver driver session."""
        if self.driver is not None:
            logger.info("Closing Appium WebDriver session...")
            try:
                self.driver.quit()
            except Exception:
                pass
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

    reader = SchemaReaderAgent()
    events = reader.run()
    planner = CrawlPlannerAgent()
    plans = planner.run(events, current_screen="home")

    if not plans:
        print("No crawl plans generated. Exiting.")
        sys.exit(0)

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
