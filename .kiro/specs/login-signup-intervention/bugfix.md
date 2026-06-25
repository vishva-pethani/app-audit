# Bugfix Requirements Document

## Introduction

During automated APK crawling, the `CrawlExecutorAgent` (Agent 4) may encounter a login or signup screen on the Android device. When this happens, the crawler is expected to pause and let the user decide how to proceed via a Streamlit popup dialog. The current implementation is incomplete in several critical ways: the "Auto-Inject" code path does nothing useful, the `InteractionBridge` cannot store credentials, the UI offers no way to enter field values or select escape buttons, login detection keywords are too broad, and no field detection or injection logic exists. This bugfix addresses all of these gaps to make the login/signup intervention flow fully functional.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the user selects "Proceed / Auto-Inject" on the login intervention popup THEN the system logs "continuing with standard executor flow" and takes no further action, leaving the login form untouched.

1.2 WHEN the user selects "Login" or "Sign Up" as their intervention decision THEN the system has no UI to collect credential values (email, password, OTP, phone, etc.) because the `InteractionBridge` only stores a single `user_decision` string.

1.3 WHEN the user selects "Login" or "Sign Up" and credentials are needed THEN the system has no mechanism to find each input field on the device screen and type values into them.

1.4 WHEN a login/signup screen contains "Skip", "Continue as Guest", "Skip Login", "Maybe Later", or similar escape buttons THEN the system does not detect these elements and does not present them as options to the user.

1.5 WHEN the login intervention popup is displayed THEN the system shows only three generic buttons (Auto-Inject, Skip/Go Back, Abort) with no dynamic form for credentials and no list of available escape options.

1.6 WHEN the screen keyword scanner evaluates a UI node THEN the keyword list includes "password", which matches non-login screens (e.g., account settings, security pages) and causes false-positive login detection triggers.

1.7 WHEN a login/signup screen is detected THEN the system does not scan for the types of input fields present (email, phone, password, OTP, etc.) and does not report them to the frontend so the user knows what to fill in.

### Expected Behavior (Correct)

2.1 WHEN the user selects "Login" or "Sign Up" from the intervention popup and submits filled credentials THEN the system SHALL locate each identified input field on the device screen, type the corresponding value into it, and attempt to submit the form.

2.2 WHEN the `InteractionBridge` is used to communicate between the frontend and the crawler THEN it SHALL store a structured credentials payload (mapping field names/types to their values) in addition to the user's decision string.

2.3 WHEN a login/signup screen is detected THEN the system SHALL scan the current UI hierarchy for input fields (email, phone, password, OTP, etc.) and populate `InteractionBridge` with the discovered field list before signalling the frontend.

2.4 WHEN a login/signup screen is detected THEN the system SHALL scan the current UI hierarchy for escape/skip elements (matching labels such as "Skip", "Skip Login", "Continue as Guest", "Guest", "Maybe Later", "Not Now") and populate `InteractionBridge` with any discovered escape options before signalling the frontend.

2.5 WHEN the login intervention popup is rendered in the Streamlit UI THEN it SHALL display a dynamic credential input form whose fields match those discovered on the device screen, plus separate options for each detected escape button, a "Go Back" option, and an "Abort" option.

2.6 WHEN the user selects an escape option (e.g., "Tap 'Continue as Guest'") from the intervention popup THEN the system SHALL tap the corresponding UI element on the device screen.

2.7 WHEN the login/signup keyword scanner evaluates a UI node THEN it SHALL require a combination of at least two distinct login-signal keywords (e.g., "login"+"password", "sign in"+"email") or a high-confidence single keyword (e.g., "sign in", "create account") before triggering intervention, so that standalone "password" matches on non-login screens do not cause false positives.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN no login/signup screen is present during a crawl step THEN the system SHALL CONTINUE TO execute crawl steps without pausing or signalling the frontend.

3.2 WHEN the user selects "Go Back" from the intervention popup THEN the system SHALL CONTINUE TO press the Android back button to navigate away from the login screen.

3.3 WHEN the user selects "Abort" from the intervention popup THEN the system SHALL CONTINUE TO raise an exception that stops the audit pipeline.

3.4 WHEN a crawl step completes normally (no login screen encountered) THEN the system SHALL CONTINUE TO dismiss unrelated popups and proceed to the next step without delay.

3.5 WHEN the `InteractionBridge` signals `login_detected` THEN the system SHALL CONTINUE TO block the crawler thread on `user_responded` until the user makes a choice, preventing the crawler from advancing past the login screen prematurely.

3.6 WHEN the Streamlit polling loop is running THEN it SHALL CONTINUE TO refresh the console log output and check pipeline thread status at the existing polling interval.
