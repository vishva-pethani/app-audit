import os
import sys
import time
from typing import Literal
from core.logger import get_logger
from core.models import CrawlPlan, CrawlStep, ExpectedEvent

logger = get_logger(__name__)

class CrawlExecutorAgent:
    """
    Agent4 CrawlExecutorAgent:
    Performs UI interactions on a connected Android device via Appium
    by executing sequentially sorted CrawlPlan steps.
    """
    def __init__(self, apk_path: str, appium_server_url: str | None = None, app_package: str | None = None, interaction_bridge=None):
        from core.config import get_settings
        settings = get_settings()
        
        self.apk_path = apk_path
        self.appium_server_url = appium_server_url or settings.APPIUM_SERVER_URL
        self.app_package = app_package or settings.ANDROID_APP_PACKAGE
        self.bridge = interaction_bridge
        
        if not self.app_package:
            raise ValueError(
                "ANDROID_APP_PACKAGE must be defined in your .env file "
                "or passed explicitly to CrawlExecutorAgent."
            )
        self.driver = None
        self.logger = logger

    def _detect_login_screen_info(self, root):
        """
        Scans the UI hierarchy to find:
        - Whether this is actually a login/signup screen (smarter keyword matching)
        - Input fields (email, phone, password, OTP, etc.)
        - Escape/skip buttons (Skip, Continue as Guest, etc.)
        Returns (is_login_screen, fields, escape_options)
        """
        # High-confidence single keywords — one is enough
        HIGH_CONF = {"sign in", "log in", "login", "signin", "sign up", "signup",
                     "create account", "register", "forgot password", "create an account"}
        # Low-confidence keywords — need at least 2 different ones present
        LOW_CONF = {"password", "email", "mobile", "phone", "otp", "verification code",
                    "continue with", "enter your"}
        # Escape button labels
        ESCAPE_LABELS = {"skip", "skip login", "skip sign in", "continue as guest", "guest",
                         "maybe later", "not now", "no thanks", "browse", "explore",
                         "continue without", "skip for now"}

        high_hits = set()
        low_hits = set()
        fields = []
        escape_options = []

        for node in root.iter():
            text = (node.attrib.get('text') or '').strip()
            desc = (node.attrib.get('content-desc') or '').strip()
            res_id = (node.attrib.get('resource-id') or '').lower()
            cls = (node.attrib.get('class') or '').lower()
            combined_lower = f"{text.lower()} {desc.lower()} {res_id}"

            # Check high-confidence login keywords
            for kw in HIGH_CONF:
                if kw in combined_lower:
                    high_hits.add(kw)

            # Check low-confidence keywords
            for kw in LOW_CONF:
                if kw in combined_lower:
                    low_hits.add(kw)

            # Detect input fields (EditText nodes)
            if 'edittext' in cls:
                label = text or desc
                # Infer field type from hint/text/resource-id
                combined_for_type = combined_lower
                if any(k in combined_for_type for k in ("password", "pass")):
                    field_type = "password"
                elif any(k in combined_for_type for k in ("otp", "verification", "code", "pin")):
                    field_type = "otp"
                elif any(k in combined_for_type for k in ("phone", "mobile", "number")):
                    field_type = "phone"
                elif any(k in combined_for_type for k in ("email", "mail")):
                    field_type = "email"
                else:
                    field_type = "text"
                # Use hint attribute if text is empty
                hint = (node.attrib.get('hint') or '').strip()
                display_label = label or hint or field_type.capitalize()
                rid = node.attrib.get('resource-id') or ''
                fields.append({"label": display_label, "resource_id": rid, "field_type": field_type})

            # Detect escape/skip buttons
            text_lower = text.lower()
            for esc in ESCAPE_LABELS:
                if esc in text_lower or esc in desc.lower():
                    rid = node.attrib.get('resource-id') or ''
                    escape_options.append({"label": text or desc, "resource_id": rid})
                    break

        is_login = bool(high_hits) or len(low_hits) >= 2
        return is_login, fields, escape_options

    def _inject_credentials(self, fields: list, credentials: dict):
        """Types credential values into matching input fields on screen."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException

        for field in fields:
            rid = field.get("resource_id", "")
            label = field.get("label", "")
            value = credentials.get(rid) or credentials.get(label) or ""
            if not value:
                logger.warning(f"No value provided for field '{label}' ({rid}), skipping.")
                continue
            try:
                if rid:
                    el = self.driver.find_element(AppiumBy.ID, rid)
                else:
                    el = self._find_element_by_strategy(label, "text")
                el.click()
                el.clear()
                el.send_keys(value)
                logger.info(f"Injected value into field '{label}' ({rid})")
                time.sleep(0.5)
            except NoSuchElementException:
                logger.warning(f"Could not find field '{label}' ({rid}) to inject value.")
            except Exception as e:
                logger.warning(f"Error injecting into field '{label}': {e}")

    def _tap_submit_button(self):
        """Tries to tap a submit/login/continue button after credential injection."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException

        submit_labels = ["login", "log in", "sign in", "signin", "submit",
                         "continue", "next", "proceed", "verify"]
        for label in submit_labels:
            try:
                el = self.driver.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().textContains("{label}").clickable(true)'
                )
                if el and el.is_displayed():
                    logger.info(f"Tapping submit button: '{label}'")
                    el.click()
                    time.sleep(2)
                    return
            except NoSuchElementException:
                pass
            except Exception:
                pass
        logger.warning("Could not find a submit button — pressing Enter as fallback.")
        try:
            from appium.webdriver.common.appiumby import AppiumBy
            from selenium.webdriver.common.keys import Keys
            self.driver.press_keycode(66)  # KEYCODE_ENTER
        except Exception as e:
            logger.warning(f"Enter key fallback failed: {e}")

    def _tap_escape_option(self, escape_label_or_rid: str):
        """Taps a skip/escape element by resource-id or text label."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException

        # Try resource-id first
        if escape_label_or_rid and ':id/' in escape_label_or_rid:
            try:
                el = self.driver.find_element(AppiumBy.ID, escape_label_or_rid)
                if el and el.is_displayed():
                    el.click()
                    logger.info(f"Tapped escape element by resource-id: {escape_label_or_rid}")
                    time.sleep(1.5)
                    return
            except NoSuchElementException:
                pass

        # Fall back to text match
        try:
            el = self.driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().textContains("{escape_label_or_rid}")'
            )
            if el and el.is_displayed():
                el.click()
                logger.info(f"Tapped escape element by text: {escape_label_or_rid}")
                time.sleep(1.5)
                return
        except NoSuchElementException:
            pass

        logger.warning(f"Could not find escape element '{escape_label_or_rid}', pressing Back instead.")
        self.driver.back()

    def _check_login_intervention(self):
        """Checks if login/signup options are visible on screen, and triggers interaction bridge if configured."""
        if not self.bridge:
            return

        try:
            from core.ui_hierarchy import dump_hierarchy, parse_hierarchy
            xml_str = dump_hierarchy(self.driver)
            root = parse_hierarchy(xml_str)
            if root is None:
                return

            is_login, fields, escape_options = self._detect_login_screen_info(root)

            if not is_login:
                return

            logger.info(f"🔑 Login/signup screen detected! Fields={[f['label'] for f in fields]}, Escapes={[e['label'] for e in escape_options]}")

            # Populate bridge with discovered screen info
            self.bridge.screen_hierarchy = xml_str
            self.bridge.discovered_fields = fields
            self.bridge.discovered_escape_options = escape_options
            self.bridge.user_decision = None
            self.bridge.credentials = {}
            self.bridge.user_responded.clear()
            self.bridge.login_detected.set()

            # Wait for user to pick an action (login / signup / escape / skip / abort)
            self.bridge.user_responded.wait()
            decision = self.bridge.user_decision
            logger.info(f"User responded with decision: {decision}")

            self.bridge.login_detected.clear()

            if decision == "abort":
                raise Exception("Audit pipeline aborted by user choice on login screen.")

            elif decision == "skip":
                logger.info("User chose Go Back — pressing Android back button.")
                try:
                    self.driver.back()
                except Exception as e:
                    logger.warning(f"Failed to go back: {e}")

            elif decision in ("login", "signup"):
                creds = self.bridge.credentials or {}
                logger.info(f"User chose {decision} — injecting {len(creds)} credential field(s).")
                self._inject_credentials(fields, creds)
                time.sleep(0.5)
                self._tap_submit_button()

            elif decision and decision.startswith("escape:"):
                target = decision[len("escape:"):]
                logger.info(f"User chose escape option: {target}")
                self._tap_escape_option(target)

            else:
                logger.warning(f"Unknown decision '{decision}' — continuing without action.")

        except Exception as e:
            if "aborted by user" in str(e):
                raise
            logger.error(f"Error in login intervention: {e}")

    def _build_driver(self):
        """Initializes the Appium WebDriver driver connection."""
        from appium import webdriver
        from appium.options.android import UiAutomator2Options

        logger.info(f"Connecting to Appium server at {self.appium_server_url}...")
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.app = self.apk_path
        options.app_package = self.app_package
        options.automation_name = "UiAutomator2"
        options.no_reset = True
        options.auto_grant_permissions = True

        self.driver = webdriver.Remote(self.appium_server_url, options=options)
        logger.info("Appium driver successfully created and connected. Waiting 8s for splash screen to complete...")
        time.sleep(8)
        self._ensure_on_main_screen()

    def _ensure_on_main_screen(self):
        """Checks if the main navigation tabs are visible, and presses back if they aren't."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException

        logger.info("Ensuring app is on the main screen...")
        
        for attempt in range(4):
            # First, check and dismiss any popups
            self._dismiss_popups()
            self._check_login_intervention()
            
            # Check if our app package is in the foreground
            try:
                curr_pkg = self.driver.current_package
                if curr_pkg and curr_pkg != self.app_package:
                    logger.info(f"App package {self.app_package} is not in foreground (currently {curr_pkg}). Relaunching...")
                    self.driver.activate_app(self.app_package)
                    time.sleep(4)
                    continue
            except Exception as e:
                logger.warning(f"Could not check current package: {e}")
            
            try:
                # Use a zero-wait find to check if 'My RE' tab is visible
                tab = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, "My RE")
                if tab and tab.is_displayed():
                    logger.info("Main screen tab 'My RE' is visible.")
                    return
            except NoSuchElementException:
                pass

            try:
                # Also check text "My RE"
                tab = self.driver.find_element(AppiumBy.XPATH, '//*[@text="My RE"]')
                if tab and tab.is_displayed():
                    logger.info("Main screen tab 'My RE' (by text) is visible.")
                    return
            except NoSuchElementException:
                pass

            # Check if we are still on the splash screen activity
            try:
                curr_act = self.driver.current_activity
                if curr_act and "SplashScreenActivity" in curr_act:
                    logger.info(f"Still on splash screen ({curr_act}). Waiting 3s...")
                    time.sleep(3)
                    continue
            except Exception as e:
                logger.warning(f"Could not check current activity: {e}")

            logger.info(f"Main screen not detected (attempt {attempt + 1}/4). Pressing back button...")
            try:
                self.driver.back()
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Failed to press back: {e}")

    def _dismiss_popups(self):
        """Auto-dismisses known popups/dialogs to prevent UI lockout."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException

        # 1. App-specific login warning dialog close button
        try:
            close_btn = self.driver.find_element(AppiumBy.ID, f"{self.app_package}:id/close_btn")
            if close_btn and close_btn.is_displayed():
                logger.info("Auto-dismiss: Found app login alert close button. Dismissing...")
                close_btn.click()
                time.sleep(1.5)
        except NoSuchElementException:
            pass
        except Exception as e:
            logger.warning(f"Error auto-dismissing popups: {e}")

        # 2. System permissions dialogs (Notification, Location)
        try:
            for btn_text in ["Allow", "While using the app", "Only this time"]:
                xpath = f'//*[@text="{btn_text}" and contains(@package, "permissioncontroller")]'
                try:
                    sys_btn = self.driver.find_element(AppiumBy.XPATH, xpath)
                    if sys_btn and sys_btn.is_displayed():
                        logger.info(f"Auto-dismiss: Found system permission button '{btn_text}'. Dismissing...")
                        sys_btn.click()
                        time.sleep(1.5)
                except NoSuchElementException:
                    pass
        except Exception as e:
            logger.warning(f"Error checking system permission popups: {e}")

    def _find_element_by_strategy(self, target_selector: str, strategy: str):
        """Finds elements using explicit waits and selector strategies, with scroll fallback."""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        # Use a shorter wait first (e.g. 5 seconds) to allow fast fallback if scroll is needed
        wait = WebDriverWait(self.driver, 5)

        for attempt in range(2):
            try:
                if strategy == "text":
                    clean_selector = target_selector.strip('"\'')
                    try:
                        escaped = clean_selector.replace('"', '\\"')
                        return wait.until(EC.presence_of_element_located((
                            AppiumBy.ANDROID_UIAUTOMATOR,
                            f'new UiSelector().text("{escaped}")'
                        )))
                    except Exception:
                        try:
                            escaped = clean_selector.replace('"', '\\"')
                            return wait.until(EC.presence_of_element_located((
                                AppiumBy.ANDROID_UIAUTOMATOR,
                                f'new UiSelector().textContains("{escaped}")'
                            )))
                        except Exception:
                            # Fallback to XPath
                            try:
                                return wait.until(EC.presence_of_element_located((
                                    AppiumBy.XPATH,
                                    f'//*[@text="{target_selector}"]'
                                )))
                            except Exception:
                                return wait.until(EC.presence_of_element_located((
                                    AppiumBy.XPATH,
                                    f'//*[contains(@text,"{target_selector}")]'
                                )))
                elif strategy == "resource_id":
                    selector = target_selector
                    if ":" not in selector and not selector.startswith("android:"):
                        selector = f"{self.app_package}:id/{selector}"
                    return wait.until(EC.presence_of_element_located((AppiumBy.ID, selector)))
                elif strategy in ("content_desc", "accessibility_id"):
                    return wait.until(EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, target_selector)))
                else:
                    raise ValueError(f"Unsupported selector strategy: {strategy}")
            except (TimeoutException, NoSuchElementException) as err:
                if attempt == 0:
                    logger.info(f"Target '{target_selector}' not found on first try. Swiping up/scrolling down...")
                    try:
                        size = self.driver.get_window_size()
                        width = size['width']
                        height = size['height']
                        self.driver.swipe(
                            int(width * 0.5), int(height * 0.8),
                            int(width * 0.5), int(height * 0.2),
                            800
                        )
                        time.sleep(2)
                    except Exception as swipe_err:
                        logger.warning(f"Failed to swipe: {swipe_err}")
                else:
                    raise NoSuchElementException(
                        f"Could not find element matching '{target_selector}' with strategy '{strategy}' even after scrolling."
                    )

    def execute_step(self, step: CrawlStep) -> bool:
        """Executes a single step action on the device UI."""
        logger.info(f"Executing step {step.step_order}: {step.action_type} target={step.target_selector} strategy={step.selector_strategy}")
        
        # Pre-step popup cleanup and login check
        self._dismiss_popups()
        self._check_login_intervention()

        try:
            if step.action_type == "tap":
                el = self._find_element_by_strategy(step.target_selector, step.selector_strategy)
                el.click()
            elif step.action_type == "input":
                el = self._find_element_by_strategy(step.target_selector, step.selector_strategy)
                el.clear()
                el.send_keys(step.value or "")
            elif step.action_type == "wait":
                duration = int(step.value) if step.value else 2
                time.sleep(duration)
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
        finally:
            # Post-step popup cleanup and login check
            self._dismiss_popups()
            self._check_login_intervention()

    def execute_plan(self, plan: CrawlPlan, event: ExpectedEvent | None = None) -> bool:
        """Runs the complete ordered steps in a CrawlPlan."""
        if event is not None:
            self.logger.debug(f"execute_plan called for event '{event.event_name}'. Checking login states.")
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
        """Safely tears down the Appium WebDriver driver session with a timeout."""
        if self.driver is not None:
            logger.info("Closing Appium WebDriver session...")
            import threading
            
            def perform_quit(driver_instance):
                try:
                    driver_instance.quit()
                except Exception as quit_err:
                    logger.warning(f"Error in driver.quit() thread: {quit_err}")

            quit_thread = threading.Thread(target=perform_quit, args=(self.driver,), daemon=True)
            quit_thread.start()
            quit_thread.join(timeout=5.0)
            if quit_thread.is_alive():
                logger.warning("Appium WebDriver quit timed out after 5.0 seconds. Continuing.")
            else:
                logger.info("Appium WebDriver session closed successfully.")
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
