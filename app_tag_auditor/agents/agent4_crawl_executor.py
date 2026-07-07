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
        # Set to True when the Appium/UiAutomator2 instrumentation has crashed
        # mid-session.  All subsequent calls will fail — events are skipped until
        # the session is successfully restarted.
        self._session_dead = False

    def _detect_login_screen_info(self, root):
        """
        Scans the UI hierarchy to determine whether the current screen is an
        interactive login/signup screen, and returns any input fields and
        escape/skip options found.

        Rules to avoid false positives:
        - Must have at least one EditText input field on screen (a login screen
          without an input field doesn't need intervention).
        - AND either a high-confidence login keyword OR 2+ low-confidence keywords.
        - High-confidence keywords are exact auth-screen labels, not generic words
          that appear on profile/settings screens.

        Returns (is_login_screen, fields, escape_options)
        """
        # High-confidence: these words appear almost exclusively on auth screens.
        # Deliberately excludes "register" (too generic — "register vehicle", etc.)
        # and "forgot password" (appears in settings/security pages too).
        HIGH_CONF = {
            "sign in", "log in", "login", "signin",
            "sign up", "signup", "create account", "create an account",
        }
        # Low-confidence: individually too common, but 2+ together signal auth.
        LOW_CONF = {
            "password", "otp", "verification code", "enter your",
        }
        # Escape button labels — tight list, avoids generic nav words.
        ESCAPE_LABELS = {
            "skip login", "skip sign in", "skip sign up",
            "continue as guest", "continue without login",
            "maybe later", "not now", "no thanks",
            "skip for now",
        }
        # Single-word escapes only matched on buttons (clickable elements).
        ESCAPE_SINGLE = {"skip", "guest"}

        high_hits = set()
        low_hits = set()
        fields = []
        escape_options = []

        for node in root.iter():
            text = (node.attrib.get('text') or '').strip()
            desc = (node.attrib.get('content-desc') or '').strip()
            res_id = (node.attrib.get('resource-id') or '').lower()
            cls = (node.attrib.get('class') or '').lower()
            clickable = node.attrib.get('clickable', 'false').lower() == 'true'
            text_lower = text.lower()
            desc_lower = desc.lower()
            combined_lower = f"{text_lower} {desc_lower} {res_id}"

            # High-confidence: full-phrase match only (not substring of longer words)
            for kw in HIGH_CONF:
                # Use word-boundary style check: the keyword must appear as a
                # standalone phrase, not as part of "registered", "login_button_id", etc.
                import re as _re
                if _re.search(r'(?<![a-z])' + _re.escape(kw) + r'(?![a-z])', combined_lower):
                    high_hits.add(kw)

            # Low-confidence
            for kw in LOW_CONF:
                if kw in combined_lower:
                    low_hits.add(kw)

            # Detect input fields (EditText nodes only)
            if 'edittext' in cls:
                hint = (node.attrib.get('hint') or '').strip()
                label = text or desc or hint
                combined_for_type = f"{combined_lower} {hint.lower()}"
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
                display_label = label or field_type.capitalize()
                rid = node.attrib.get('resource-id') or ''
                fields.append({"label": display_label, "resource_id": rid, "field_type": field_type})

            # Detect escape/skip buttons
            # Multi-word escapes: match anywhere in text/desc
            for esc in ESCAPE_LABELS:
                if esc in text_lower or esc in desc_lower:
                    rid = node.attrib.get('resource-id') or ''
                    escape_options.append({"label": text or desc, "resource_id": rid})
                    break
            else:
                # Single-word escapes: only on clickable elements to avoid nav tabs
                if clickable:
                    for esc in ESCAPE_SINGLE:
                        if text_lower == esc or desc_lower == esc:
                            rid = node.attrib.get('resource-id') or ''
                            escape_options.append({"label": text or desc, "resource_id": rid})
                            break

        # Require BOTH: at least one input field AND auth keywords.
        # A screen with no EditText is not an interactive login screen.
        has_auth_keywords = bool(high_hits) or len(low_hits) >= 2
        is_login = bool(fields) and has_auth_keywords
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
        """
        Tries every reasonable strategy to submit a login/signup form, in order:
        1. Text-based clickable button matching common submit labels
        2. Content-description based (arrow icons, forward icons, etc.)
        3. Any clickable ImageButton or ImageView near the bottom half of screen (arrow/forward icon)
        4. IME action button on the last focused field (Done / Go / Next)
        5. KEYCODE_ENTER on the currently focused field
        6. Focus-out (tap outside the field) — sometimes triggers validation + submit
        7. KEYCODE_TAB to move focus off the last field, then KEYCODE_ENTER
        Falls through all strategies so it never blocks.
        """
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException, WebDriverException

        # ── Strategy 1: Text-based clickable buttons ────────────────────────
        submit_labels = [
            "login", "log in", "sign in", "signin",
            "sign up", "signup", "register", "create account",
            "submit", "continue", "next", "proceed",
            "verify", "send otp", "get otp", "confirm",
        ]
        for label in submit_labels:
            try:
                el = self.driver.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().textContains("{label}").clickable(true)'
                )
                if el and el.is_displayed():
                    logger.info(f"[Submit] Strategy 1 — tapping text button: '{label}'")
                    el.click()
                    time.sleep(2)
                    return
            except (NoSuchElementException, WebDriverException):
                pass

        # ── Strategy 2: Content-description arrow/forward icons ─────────────
        arrow_descs = [
            "next", "continue", "forward", "arrow", "go", "proceed",
            "submit", "done", "→", "›",
        ]
        for desc in arrow_descs:
            try:
                el = self.driver.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().descriptionContains("{desc}").clickable(true)'
                )
                if el and el.is_displayed():
                    logger.info(f"[Submit] Strategy 2 — tapping by content-desc: '{desc}'")
                    el.click()
                    time.sleep(2)
                    return
            except (NoSuchElementException, WebDriverException):
                pass

        # ── Strategy 3: Clickable ImageButton / ImageView in lower half ──────
        try:
            size = self.driver.get_window_size()
            mid_y = size['height'] // 2
            # Find all clickable image buttons; prefer ones in the lower half
            candidates = self.driver.find_elements(
                AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().clickable(true).className("android.widget.ImageButton")'
            )
            candidates += self.driver.find_elements(
                AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().clickable(true).className("android.widget.ImageView")'
            )
            lower_candidates = [
                el for el in candidates
                if el.is_displayed() and el.location.get('y', 0) > mid_y
            ]
            if lower_candidates:
                # Pick the rightmost one (typical for arrow/forward button placement)
                best = max(lower_candidates, key=lambda e: e.location.get('x', 0))
                logger.info(f"[Submit] Strategy 3 — tapping ImageButton/View at {best.location}")
                best.click()
                time.sleep(2)
                return
        except Exception as e:
            logger.debug(f"[Submit] Strategy 3 failed: {e}")

        # ── Strategy 4: IME action button (Done / Go / Next on keyboard) ─────
        try:
            # KEYCODE_EDITOR_ACTION fires the IME action configured on the field
            self.driver.press_keycode(160)  # KEYCODE_EDITOR_ACTION
            logger.info("[Submit] Strategy 4 — pressed KEYCODE_EDITOR_ACTION (IME action)")
            time.sleep(1.5)
            # Check if we moved off the login screen (a proxy for success)
            from core.ui_hierarchy import dump_hierarchy, parse_hierarchy
            xml_str = dump_hierarchy(self.driver)
            root = parse_hierarchy(xml_str)
            if root is not None:
                still_login, _, _ = self._detect_login_screen_info(root)
                if not still_login:
                    logger.info("[Submit] Strategy 4 — IME action appears to have worked.")
                    return
        except Exception as e:
            logger.debug(f"[Submit] Strategy 4 failed: {e}")

        # ── Strategy 5: KEYCODE_ENTER on focused field ───────────────────────
        try:
            self.driver.press_keycode(66)  # KEYCODE_ENTER
            logger.info("[Submit] Strategy 5 — pressed KEYCODE_ENTER")
            time.sleep(1.5)
            from core.ui_hierarchy import dump_hierarchy, parse_hierarchy
            xml_str = dump_hierarchy(self.driver)
            root = parse_hierarchy(xml_str)
            if root is not None:
                still_login, _, _ = self._detect_login_screen_info(root)
                if not still_login:
                    logger.info("[Submit] Strategy 5 — Enter appears to have worked.")
                    return
        except Exception as e:
            logger.debug(f"[Submit] Strategy 5 failed: {e}")

        # ── Strategy 6: Focus-out — tap centre of screen outside any field ───
        try:
            size = self.driver.get_window_size()
            tap_x = size['width'] // 2
            tap_y = int(size['height'] * 0.85)  # near bottom, outside typical field area
            self.driver.tap([(tap_x, tap_y)])
            logger.info(f"[Submit] Strategy 6 — focus-out tap at ({tap_x}, {tap_y})")
            time.sleep(1)
        except Exception as e:
            logger.debug(f"[Submit] Strategy 6 failed: {e}")

        # ── Strategy 7: TAB then ENTER ───────────────────────────────────────
        try:
            self.driver.press_keycode(61)   # KEYCODE_TAB
            time.sleep(0.5)
            self.driver.press_keycode(66)   # KEYCODE_ENTER
            logger.info("[Submit] Strategy 7 — TAB + ENTER")
            time.sleep(1.5)
        except Exception as e:
            logger.debug(f"[Submit] Strategy 7 failed: {e}")

        logger.warning("[Submit] All submit strategies exhausted — continuing without confirmed submission.")

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

            # ── Mid-login mode: credentials already submitted, now on a follow-up
            #    screen (OTP, verification, etc.). Skip the choice popup — just
            #    detect new fields, ask user to fill them, inject and submit.
            if getattr(self.bridge, 'login_in_progress', False):
                if not fields:
                    logger.debug("Login in progress, sub-screen has no new input fields — skipping.")
                    return

                logger.info(f"🔢 Mid-login sub-screen detected (OTP/verification). Fields={[f['label'] for f in fields]}")

                # Reuse bridge to ask for field values — signal with a special decision
                self.bridge.screen_hierarchy = xml_str
                self.bridge.discovered_fields = fields
                self.bridge.discovered_escape_options = []
                self.bridge.user_decision = None
                self.bridge.credentials = {}
                self.bridge.user_responded.clear()
                # Set a flag so the UI knows this is a mid-login field-fill (not the initial choice)
                self.bridge.mid_login_fields = True
                self.bridge.login_detected.set()

                self.bridge.user_responded.wait()
                decision = self.bridge.user_decision
                self.bridge.login_detected.clear()
                self.bridge.mid_login_fields = False

                if decision == "abort":
                    raise Exception("Audit pipeline aborted by user on OTP/verification screen.")
                elif decision in ("login", "signup", "submit_fields"):
                    creds = self.bridge.credentials or {}
                    logger.info(f"Injecting {len(creds)} field value(s) on sub-screen.")
                    self._inject_credentials(fields, creds)
                    time.sleep(0.5)
                    self._tap_submit_button()
                elif decision == "skip":
                    logger.info("User chose to skip OTP/sub-screen — pressing Back.")
                    self.bridge.login_in_progress = False
                    try:
                        self.driver.back()
                    except Exception as e:
                        logger.warning(f"Failed to go back: {e}")
                return

            # ── First encounter: show the full choice popup ──────────────────
            logger.info(f"🔑 Login/signup screen detected! Fields={[f['label'] for f in fields]}, Escapes={[e['label'] for e in escape_options]}")

            self.bridge.screen_hierarchy = xml_str
            self.bridge.discovered_fields = fields
            self.bridge.discovered_escape_options = escape_options
            self.bridge.mid_login_fields = False
            self.bridge.user_decision = None
            self.bridge.credentials = {}
            self.bridge.user_responded.clear()
            self.bridge.login_detected.set()

            self.bridge.user_responded.wait()
            decision = self.bridge.user_decision
            logger.info(f"User responded with decision: {decision}")

            self.bridge.login_detected.clear()

            if decision == "abort":
                raise Exception("Audit pipeline aborted by user choice on login screen.")

            elif decision == "skip":
                logger.info("User chose Go Back — pressing Android back button.")
                self.bridge.login_in_progress = False
                try:
                    self.driver.back()
                except Exception as e:
                    logger.warning(f"Failed to go back: {e}")

            elif decision in ("login", "signup"):
                creds = self.bridge.credentials or {}
                logger.info(f"User chose {decision} — injecting {len(creds)} credential field(s).")
                self.bridge.login_in_progress = True
                self._inject_credentials(fields, creds)
                time.sleep(0.5)
                self._tap_submit_button()

            elif decision and decision.startswith("escape:"):
                target = decision[len("escape:"):]
                logger.info(f"User chose escape option: {target}")
                self.bridge.login_in_progress = False
                self._tap_escape_option(target)

            else:
                logger.warning(f"Unknown decision '{decision}' — continuing without action.")

        except Exception as e:
            if "aborted by user" in str(e):
                raise
            logger.error(f"Error in login intervention: {e}")

    def _is_session_crash_error(self, exc: Exception) -> bool:
        """
        Returns True when the exception signals that the UiAutomator2
        instrumentation process has crashed and the session is unrecoverable
        without a full restart.
        """
        msg = str(exc).lower()
        crash_phrases = [
            "instrumentation process is not running",
            "instrumentation process cannot be initialized",
            "cannot be proxied",
            "target app crashed",
            "uiautomator2 server",
            "session not found",
            "invalid session id",
            "no such session",
        ]
        return any(phrase in msg for phrase in crash_phrases)

    def _try_restart_session(self) -> bool:
        """
        Attempts to tear down the dead session and create a fresh one.
        Uses force_reinstall=True to clear stale UiAutomator2 server state
        that causes immediate instrumentation crashes on reconnect.
        Returns True on success, False if restart also fails.
        """
        logger.warning("Attempting Appium session restart after crash...")
        # Tear down the dead session gracefully (best-effort)
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        # Brief pause to let adb/UiAutomator2 release resources on the device
        time.sleep(3)

        self._session_dead = False
        try:
            # force_reinstall=True: tells Appium to reinstall the UiAutomator2
            # server APK, clearing any corrupted state from the previous crash.
            self._build_driver(force_reinstall=True)
            logger.info("Appium session restarted successfully.")
            return True
        except Exception as restart_err:
            logger.error(f"Session restart failed: {restart_err}")
            self._session_dead = True
            return False

    def _build_driver(self, force_reinstall: bool = False):
        """Initializes the Appium WebDriver driver connection.
        
        Args:
            force_reinstall: When True, forces UiAutomator2 server reinstall
                             (used during crash recovery to clear stale server state).
        """
        from appium import webdriver
        from appium.options.android import UiAutomator2Options

        # ── Ensure ANDROID_HOME / ANDROID_SDK_ROOT are available ──────────────
        # The Appium uiautomator2 driver requires these to locate adb and SDK
        # tools. When the app is launched via Streamlit directly (not through the
        # systemd launcher), these vars may not be set in the shell environment.
        # We resolve the SDK path from: env var → known installation path → system adb.
        KNOWN_SDK_PATHS = [
            # Windows default
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Android", "Sdk"),
            r"C:\Android\Sdk",
            # Linux / macOS defaults
            os.path.expanduser("~/Android/Sdk"),
            "/opt/app-tag-auditor/android-sdk",
            "/usr/lib/android-sdk",
        ]
        sdk_root = (
            os.environ.get("ANDROID_HOME")
            or os.environ.get("ANDROID_SDK_ROOT")
        )
        # If the environment-provided SDK is invalid or incomplete (missing build-tools),
        # try to look for a better one in KNOWN_SDK_PATHS.
        if not sdk_root or not os.path.isdir(os.path.join(sdk_root, "build-tools")):
            # 1. Prefer SDK that has build-tools (and therefore aapt2)
            for candidate in KNOWN_SDK_PATHS:
                if (os.path.isdir(candidate) and 
                    os.path.isdir(os.path.join(candidate, "platform-tools")) and
                    os.path.isdir(os.path.join(candidate, "build-tools"))):
                    sdk_root = candidate
                    break
            # 2. Fall back to any SDK with platform-tools
            if not sdk_root:
                for candidate in KNOWN_SDK_PATHS:
                    if os.path.isdir(candidate) and os.path.isdir(os.path.join(candidate, "platform-tools")):
                        sdk_root = candidate
                        break
        if sdk_root:
            os.environ["ANDROID_HOME"] = sdk_root
            os.environ["ANDROID_SDK_ROOT"] = sdk_root
            logger.info(f"Android SDK resolved to: {sdk_root}")
        else:
            logger.warning("Could not resolve Android SDK path. ANDROID_HOME not set.")

        logger.info(f"Connecting to Appium server at {self.appium_server_url}...")
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.app = self.apk_path
        options.app_package = self.app_package
        options.automation_name = "UiAutomator2"
        options.auto_grant_permissions = True
        options.ignore_hidden_api_policy_error = True
        options.set_capability("appium:ignoreHiddenApiPolicyError", True)

        # Pass the SDK path directly as a capability so the uiautomator2 driver
        # uses it even if the Appium server process didn't inherit ANDROID_HOME.
        if sdk_root:
            options.set_capability("appium:androidSdkPath", sdk_root)

        # On normal start: no_reset=True keeps app data (faster).
        # On crash recovery: no_reset=False forces a clean reinstall of the
        # UiAutomator2 server APK — this clears stale/corrupted server state
        # that causes "instrumentation process is not running" immediately.
        options.no_reset = not force_reinstall
        if force_reinstall:
            logger.info("Force-reinstall mode: clearing UiAutomator2 server state.")
            # Allow Appium to reinstall the server and reset the instrumentation
            options.skip_server_installation = False
            options.skip_device_initialization = False

        # Increase UiAutomator2 server launch and install timeouts.
        # Default 30s is too short for large APKs or slower devices/emulators.
        options.uiautomator2_server_launch_timeout = 120000  # ms — server start
        options.uiautomator2_server_install_timeout = 120000 # ms — APK install
        options.adb_exec_timeout = 60000                     # ms — individual adb calls
        options.new_command_timeout = 300                    # s  — idle session timeout

        self.driver = webdriver.Remote(self.appium_server_url, options=options)
        logger.info("Appium driver successfully created and connected. Waiting 8s for splash screen to complete...")
        time.sleep(8)
        self._ensure_on_main_screen()

    def _ensure_on_main_screen(self):
        """
        Ensures the target app is in the foreground and past any splash screen.
        Uses package-foreground check instead of app-specific tab names so this
        works across any APK, not just Royal Enfield.
        """
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.common.exceptions import NoSuchElementException

        logger.info("Ensuring app is on the main screen...")

        # If the session is already dead, skip entirely.
        if self._session_dead:
            logger.warning("Session is dead — skipping _ensure_on_main_screen.")
            return

        # If login is in progress, the app is mid-auth flow (OTP screen, etc.).
        # Don't press Back — just wait for the user to complete it naturally.
        if self.bridge and getattr(self.bridge, 'login_in_progress', False):
            logger.info("Login in progress — skipping back-button loop in _ensure_on_main_screen.")
            return

        for attempt in range(4):
            try:
                self._dismiss_popups()
            except Exception as e:
                if self._is_session_crash_error(e):
                    logger.error(f"🔴 Session crash in _ensure_on_main_screen (dismiss popups): {e}")
                    self._session_dead = True
                    return
            try:
                self._check_login_intervention()
            except Exception as e:
                if self._is_session_crash_error(e):
                    logger.error(f"🔴 Session crash in _ensure_on_main_screen (login check): {e}")
                    self._session_dead = True
                    return

            # If login intervention was just triggered and credentials submitted,
            # the flag is now set — stop pressing back.
            if self.bridge and getattr(self.bridge, 'login_in_progress', False):
                logger.info("Login started during ensure-main-screen — stopping back-button loop.")
                return

            # Primary check: is our app package in the foreground?
            try:
                curr_pkg = self.driver.current_package
                if curr_pkg and curr_pkg == self.app_package:
                    # App is in foreground — check we're not still on splash
                    try:
                        curr_act = self.driver.current_activity
                        if curr_act and any(s in curr_act for s in ("Splash", "splash", "Loading", "loading", "Intro", "intro")):
                            logger.info(f"Still on splash/loading screen ({curr_act}). Waiting 3s...")
                            time.sleep(3)
                            continue
                    except Exception:
                        pass
                    logger.info(f"App package '{self.app_package}' is in foreground — proceeding.")
                    if self.bridge:
                        self.bridge.login_in_progress = False
                    return
                elif curr_pkg and curr_pkg != self.app_package:
                    logger.info(f"App not in foreground (currently '{curr_pkg}'). Relaunching...")
                    self.driver.activate_app(self.app_package)
                    time.sleep(4)
                    continue
            except Exception as e:
                if self._is_session_crash_error(e):
                    logger.error(f"🔴 Session crash detected in _ensure_on_main_screen: {e}")
                    self._session_dead = True
                    return
                logger.warning(f"Could not check current package: {e}")

            logger.info(f"App not confirmed in foreground (attempt {attempt + 1}/4). Pressing back...")
            try:
                self.driver.back()
                time.sleep(2)
            except Exception as e:
                if self._is_session_crash_error(e):
                    logger.error(f"🔴 Session crash on back press in _ensure_on_main_screen: {e}")
                    self._session_dead = True
                    return
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

        # Guard: never pass an empty selector to Appium — it raises an unhelpful error
        if not target_selector or not target_selector.strip():
            raise NoSuchElementException("Empty selector provided — step skipped.")

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
        # If the session is already known-dead, skip immediately.
        if self._session_dead:
            logger.warning(f"Session is dead — skipping step {step.step_order} ({step.action_type}).")
            return False

        logger.info(f"Executing step {step.step_order}: {step.action_type} target={step.target_selector} strategy={step.selector_strategy}")

        # Only dismiss system/app popups (permission dialogs etc.) before each step.
        # Login/signup intervention is NOT checked here — it is only triggered at
        # app startup (_build_driver → _ensure_on_main_screen) and between events
        # (reset_best_effort → _ensure_on_main_screen). This prevents the auditor
        # from treating normal form fields (search, booking, profile) as auth screens.
        self._dismiss_popups()

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
            if self._is_session_crash_error(e):
                logger.error(f"🔴 UiAutomator2 session crash detected at step {step.step_order}: {e}")
                self._session_dead = True
                return False
            logger.error(f"Step {step.step_order} execution failed: {e}")
            return False
        finally:
            # Only dismiss popups after the step — no login check here.
            if not self._session_dead:
                self._dismiss_popups()

    def execute_plan(self, plan: CrawlPlan, event: ExpectedEvent | None = None) -> bool:
        """Runs the complete ordered steps in a CrawlPlan."""
        if event is not None:
            self.logger.debug(f"execute_plan called for event '{event.event_name}'. Checking login states.")

        # If previous event left the session dead, attempt a recovery restart now.
        if self._session_dead:
            logger.warning(f"Session was dead before event '{plan.event_name}'. Attempting restart...")
            recovered = self._try_restart_session()
            if not recovered:
                logger.error(f"Could not recover session for event '{plan.event_name}' — skipping.")
                return False
        elif self.driver is None:
            # First-time driver init
            self._build_driver()
            # Check if _ensure_on_main_screen inside _build_driver set _session_dead
            if self._session_dead:
                logger.warning(f"Session crashed during init for event '{plan.event_name}'. Attempting restart...")
                recovered = self._try_restart_session()
                if not recovered:
                    logger.error(f"Could not recover session after init crash for event '{plan.event_name}' — skipping.")
                    return False

        logger.info(f"Initiating CrawlPlan execution for event '{plan.event_name}'")
        sorted_steps = sorted(plan.steps, key=lambda s: s.step_order)

        for step in sorted_steps:
            success = self.execute_step(step)
            if not success:
                if self._session_dead:
                    logger.error(f"Session crashed during event '{plan.event_name}' — aborting remaining steps.")
                    return False
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
