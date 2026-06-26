import sys
import os
import streamlit as st
import pandas as pd
import logging
import queue
import threading
import time
from google.oauth2.credentials import Credentials

# Ensure the app_tag_auditor directory is in sys.path so core and frontend imports resolve correctly
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Hot reload all local modules to handle Streamlit process caching
import importlib
import sys

# Find all loaded local modules
local_modules = [
    name for name in sys.modules
    if name.startswith("core") or name.startswith("agents") or name.startswith("frontend") or name == "orchestrator"
]

# Reload core.config first so other modules get the new config reference when reloaded
if "core.config" in sys.modules:
    try:
        importlib.reload(sys.modules["core.config"])
    except Exception:
        pass
    
for mod_name in local_modules:
    if mod_name != "core.config" and mod_name in sys.modules:
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception:
            pass

# Clear cache of get_settings
try:
    import core.config
    core.config.get_settings.cache_clear()
except Exception:
    pass

from core.config import get_settings
from core.drive_client import DriveClient
from core.sheets_client import SheetsClient
import frontend.components.drive_picker as drive_picker
from orchestrator import run_pipeline

st.set_page_config(
    page_title="App Tag Auditor",
    page_icon="🔍",
    layout="wide",
)

# Custom premium styling loaded globally
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
     font-family: 'Outfit', sans-serif !important;
    background: var(--background-color) !important;
    background-color: var(--background-color) !important;
    color: var(--text-color) !important;
    overflow-x: hidden;
    overflow-y: hidden !important;
    height: 100vh !important;
}

/* Background Glowing Blobs */
.bg-glow-container {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    z-index: 0;
    overflow: hidden;
    pointer-events: none;
}
.bg-glow-orange {
    position: absolute;
    top: 15%;
    left: 20%;
    width: 450px;
    height: 450px;
    background: radial-gradient(circle, rgba(255, 143, 0, 0.05) 0%, rgba(255, 143, 0, 0) 70%);
    filter: blur(80px);
}
.bg-glow-red {
    position: absolute;
    bottom: 15%;
    right: 20%;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(239, 68, 68, 0.04) 0%, rgba(239, 68, 68, 0) 70%);
    filter: blur(90px);
}

/* Slide Up & Fade In Animations */
@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes pulseGlow {
    0% {
        box-shadow: 0 0 20px rgba(255, 143, 0, 0.2);
        border-color: rgba(255, 143, 0, 0.3);
    }
    100% {
        box-shadow: 0 0 35px rgba(255, 143, 0, 0.45);
        border-color: rgba(255, 143, 0, 0.6);
    }
}

.block-container {
    padding-top: 6rem !important;
    padding-bottom: 2rem !important;
    padding-left: 3rem !important;
    padding-right: 3rem !important;
}

section[data-testid="stMain"] {
    padding-top: 0 !important;
}

div[data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
/* Main Welcome Page Wrapper */
.welcome-wrapper {
    position: relative;
    z-index: 10;
    max-width: 460px;
    margin: 0 auto;
    min-height: calc(100vh - 8rem);
    display: flex;
    align-items: center;
    justify-content: center;
    animation: slideUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

/* Glassmorphism Card Container */
.login-card {
    background: var(--secondary-background-color) !important;
    border: 1px solid rgba(128, 128, 128, 0.15) !important;
    backdrop-filter: blur(24px) !important;
    -webkit-backdrop-filter: blur(24px) !important;
    border-radius: 24px;
    padding: 3.5rem 2.5rem;
    box-shadow: 0 15px 30px rgba(0, 0, 0, 0.08), 0 0 30px rgba(255, 143, 0, 0.03);
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.75rem;
}

/* Pulse Glowing Badge for Logo */
.logo-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 84px;
    height: 84px;
    background: radial-gradient(135deg, rgba(255, 143, 0, 0.15) 0%, rgba(239, 68, 68, 0.04) 100%);
    border: 1px solid rgba(255, 143, 0, 0.3);
    border-radius: 20px;
    margin-bottom: 0.5rem;
    animation: pulseGlow 3s infinite alternate ease-in-out;
}

/* Cinematic Title */
.login-title {
    font-size: 2.25rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.5px !important;
    margin: 0 !important;
    background: linear-gradient(135deg, #ff8f00 0%, #ef4444 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
}

/* High Contrast Description */
.login-subtitle {
    color: var(--text-color) !important;
    opacity: 0.75 !important;
    font-size: 0.975rem !important;
    line-height: 1.6 !important;
    max-width: 320px;
    margin: 0 auto 0.5rem auto !important;
}

/* Google Sign-in Button styling */
.google-login-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    background-color: var(--background-color) !important;
    color: var(--text-color) !important;
    font-weight: 600;
    font-size: 0.95rem;
    padding: 14px 24px;
    border-radius: 12px;
    text-decoration: none !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    width: 100%;
    box-sizing: border-box;
    border: 1px solid rgba(128, 128, 128, 0.2) !important;
}

.google-login-btn:hover {
    background-color: var(--secondary-background-color) !important;
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(255, 143, 0, 0.3);
}

.google-login-btn:active {
    transform: translateY(0);
}

.google-icon {
    display: block;
}

/* General app body formatting after login */
.main {
    background: transparent !important;
}

.glass-container {
    background: var(--secondary-background-color) !important;
    border-radius: 16px;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(128, 128, 128, 0.15) !important;
    padding: 2.5rem;
    margin: 2rem 0;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.08);
}

.gradient-title {
    background: linear-gradient(135deg, #ff8f00 0%, #ef4444 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 2.75rem;
    margin-bottom: 0.5rem;
}

.sub-title {
    color: var(--text-color) !important;
    opacity: 0.75 !important;
    font-size: 1.15rem;
    margin-bottom: 2rem;
}

.step-card {
    background: rgba(255, 143, 0, 0.03) !important;
    border-left: 4px solid #ff8f00 !important;
    border-radius: 4px;
    padding: 1rem;
    margin-bottom: 1rem;
}

.step-card h4 {
    margin-top: 0;
    color: #ff8f00;
}

.user-profile-card {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 15px;
    margin-bottom: 24px !important;
}
</style>
""", unsafe_allow_html=True)

settings = get_settings()

# Render CSS to hide the communication textareas
st.markdown("""
<style>
div[data-testid="stTextArea"]:has(textarea[aria-label="hidden_auth_widget"]),
div[data-testid="stTextArea"]:has(textarea[aria-label="hidden_edit_data_widget"]) {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "google_auth_token" not in st.session_state:
    st.session_state["google_auth_token"] = None
if "google_refresh_token" not in st.session_state:
    st.session_state["google_refresh_token"] = None
if "google_token_expiry" not in st.session_state:
    st.session_state["google_token_expiry"] = None
if "user_profile" not in st.session_state:
    st.session_state["user_profile"] = None

# Hidden auth restore widget
with st.container():
    auth_data_json = st.text_area("hidden_auth_widget", key="hidden_auth_widget", value="")

if auth_data_json and not st.session_state["authenticated"]:
    try:
        import json
        auth_data = json.loads(auth_data_json)
        token = auth_data.get("token")
        refresh_token = auth_data.get("refresh_token")
        expiry = auth_data.get("expiry")
        profile = auth_data.get("profile")
        
        # Check if the access token has expired or is about to expire
        if token and refresh_token and expiry:
            import time
            import requests
            # If the token is expired or expires in less than 5 minutes (300 seconds), refresh it
            if float(expiry) < time.time() + 300:
                try:
                    refresh_res = requests.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token"
                        },
                        timeout=10
                    )
                    if refresh_res.status_code == 200:
                        new_token_data = refresh_res.json()
                        token = new_token_data.get("access_token")
                        expires_in = new_token_data.get("expires_in", 3600)
                        expiry = str(time.time() + expires_in)
                except Exception:
                    pass
                    
        if token and profile:
            st.session_state["authenticated"] = True
            st.session_state["google_auth_token"] = token
            st.session_state["google_refresh_token"] = refresh_token
            st.session_state["google_token_expiry"] = expiry
            st.session_state["user_profile"] = profile
            st.rerun()
    except Exception:
        pass

# Check if we should restore from localStorage
if not st.session_state["authenticated"] and "code" not in st.query_params:
    st.markdown("""
    <script>
    setTimeout(() => {
        const token = localStorage.getItem("google_auth_token");
        const refreshToken = localStorage.getItem("google_refresh_token");
        const expiry = localStorage.getItem("google_token_expiry");
        const profileStr = localStorage.getItem("user_profile");
        if (token && profileStr) {
            const textarea = parent.document.querySelector('textarea[aria-label="hidden_auth_widget"]') || document.querySelector('textarea[aria-label="hidden_auth_widget"]');
            if (textarea && textarea.value === "") {
                const payload = JSON.stringify({ 
                    token: token, 
                    refresh_token: refreshToken, 
                    expiry: expiry, 
                    profile: JSON.parse(profileStr) 
                });
                const lastValue = textarea.value;
                textarea.value = payload;
                const event = new Event('input', { bubbles: true });
                event.simulated = true;
                const tracker = textarea._valueTracker;
                if (tracker) {
                    tracker.setValue(lastValue);
                }
                textarea.dispatchEvent(event);
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
                textarea.blur();
            }
        }
    }, 300);
    </script>
    """, unsafe_allow_html=True)

# Check query parameters for incoming Google Authorization Code
query_params = st.query_params
if "code" in query_params:
    code = query_params["code"]
    try:
        import requests
        # Exchange authorization code for token
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI
            },
            timeout=10
        )
        if token_res.status_code == 200:
            token_data = token_res.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            expiry = str(time.time() + expires_in)
            
            # Fetch user profile using the access token
            profile_res = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if profile_res.status_code == 200:
                profile = profile_res.json()
                st.session_state["authenticated"] = True
                st.session_state["google_auth_token"] = access_token
                if refresh_token:
                    st.session_state["google_refresh_token"] = refresh_token
                st.session_state["google_token_expiry"] = expiry
                st.session_state["user_profile"] = profile
                
                # Store in localStorage on first login
                import json
                refresh_part = f'localStorage.setItem("google_refresh_token", "{refresh_token}");' if refresh_token else ''
                st.markdown(f"""
                <script>
                localStorage.setItem("google_auth_token", "{access_token}");
                {refresh_part}
                localStorage.setItem("google_token_expiry", "{expiry}");
                localStorage.setItem("user_profile", '{json.dumps(profile)}');
                </script>
                """, unsafe_allow_html=True)
                
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"Failed to retrieve user profile from Google: {profile_res.text}")
        else:
            st.error(f"Failed to exchange Google OAuth code: {token_res.text}")
    except Exception as e:
        st.error(f"Error during Google authentication exchange: {e}")

# If NOT authenticated, show the login guard page and stop execution!
if not st.session_state["authenticated"]:
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    
    # Check if client ID is configured properly
    is_btn_disabled = False
    if not client_id or client_id == "your-google-oauth-client-id.apps.googleusercontent.com":
        is_btn_disabled = True

    # Construct the Authorization URL
    import urllib.parse
    redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    scopes = "openid email profile https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets"
    encoded_scopes = urllib.parse.quote(scopes)
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&response_type=code&scope={encoded_scopes}&access_type=offline&prompt=consent"

    # Centered container for login card using columns
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        if is_btn_disabled:
            st.error("⚠️ Google Client ID is not configured. Please check your .env file.")
        else:
            login_card_html = f"""<div class="bg-glow-container">
<div class="bg-glow-orange"></div>
<div class="bg-glow-red"></div>
</div>
<div class="welcome-wrapper">
<div class="login-card">
<div class="logo-badge">
<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="#ff8f00" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 0 8px rgba(255, 143, 0, 0.5));">
<rect x="3" y="11" width="18" height="10" rx="2"></rect>
<circle cx="12" cy="5" r="2"></circle>
<path d="M12 7v4"></path>
<line x1="8" y1="16" x2="8" y2="16" stroke-linecap="round" stroke-width="2"></line>
<line x1="16" y1="16" x2="16" y2="16" stroke-linecap="round" stroke-width="2"></line>
</svg>
</div>
<h1 class="login-title">App Tag Auditor</h1>
<p class="login-subtitle">Please sign in with your Google account to access the auditing dashboard.</p>
<a href="{auth_url}" target="_self" class="google-login-btn">
<svg class="google-icon" viewBox="0 0 24 24" width="18" height="18" style="margin-right: 8px;">
<path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.275 1.565-1.88 4.604-6.887 4.604-4.33 0-7.859-3.578-7.859-8s3.53-8 7.859-8c2.46 0 4.105 1.025 5.047 1.926l3.256-3.133C18.28 1.705 15.49 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c6.478 0 10.793-4.537 10.793-10.984 0-.742-.08-1.302-.178-1.782h-10.62z"/>
</svg>
Sign in with Google
</a>
</div>
</div>"""
            st.markdown(login_card_html, unsafe_allow_html=True)
            
    st.stop()

# Custom premium styling already loaded at the top
if st.session_state.get("authenticated") and st.session_state.get("google_auth_token") and st.session_state.get("user_profile"):
    import json
    token = st.session_state["google_auth_token"]
    refresh_token = st.session_state.get("google_refresh_token", "")
    expiry = st.session_state.get("google_token_expiry", "")
    profile = st.session_state["user_profile"]
    
    # Live token expiry check and refresh if within 5 mins of expiry
    if refresh_token and expiry:
        try:
            if float(expiry) < time.time() + 300:
                import requests
                refresh_res = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    },
                    timeout=10
                )
                if refresh_res.status_code == 200:
                    new_token_data = refresh_res.json()
                    token = new_token_data.get("access_token")
                    st.session_state["google_auth_token"] = token
                    expires_in = new_token_data.get("expires_in", 3600)
                    expiry = str(time.time() + expires_in)
                    st.session_state["google_token_expiry"] = expiry
        except Exception:
            pass

    st.markdown(f"""
    <script>
    if (localStorage.getItem("google_auth_token") !== "{token}" || localStorage.getItem("google_token_expiry") !== "{expiry}") {{
        localStorage.setItem("google_auth_token", "{token}");
        if ("{refresh_token}") {{
            localStorage.setItem("google_refresh_token", "{refresh_token}");
        }}
        if ("{expiry}") {{
            localStorage.setItem("google_token_expiry", "{expiry}");
        }}
        localStorage.setItem("user_profile", '{json.dumps(profile)}');
    }}
    </script>
    """, unsafe_allow_html=True)

# Profile Header Section
if st.session_state.get("authenticated") and st.session_state.get("user_profile"):
    profile = st.session_state["user_profile"]
    col_title, col_user = st.columns([3, 1])
    with col_title:
        st.markdown('<div class="gradient-title">🔍 App Tag Auditor</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-title">Automated Firebase Analytics APK Auditing System</div>', unsafe_allow_html=True)
    with col_user:
        st.markdown(
            f"""
            <div class="user-profile-card">
                <img src="{profile.get('picture', '')}" style="width: 42px; height: 42px; border-radius: 50%; border: 2px solid #ff4b4b; box-shadow: 0 0 10px rgba(255, 75, 75, 0.3);" />
                <div style="text-align: left; line-height: 1.2;">
                    <div style="font-weight: 700; font-size: 0.95rem; color: #ffffff;">{profile.get('name', 'User')}</div>
                    <div style="font-size: 0.8rem; color: #8892b0;">{profile.get('email', '')}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("🔌 Sign Out", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["user_profile"] = None
            st.session_state["google_auth_token"] = None
            st.session_state["google_refresh_token"] = None
            st.session_state["google_token_expiry"] = None
            # Clear all selection & auth states
            for k in list(st.session_state.keys()):
                if k.startswith("google_auth_token_") or k.startswith("drive_selection_"):
                    del st.session_state[k]
            if "apk_drive" in st.session_state:
                del st.session_state["apk_drive"]
            
            st.markdown("""
            <script>
            localStorage.removeItem("google_auth_token");
            localStorage.removeItem("google_refresh_token");
            localStorage.removeItem("google_token_expiry");
            localStorage.removeItem("user_profile");
            </script>
            """, unsafe_allow_html=True)
            
            st.rerun()
else:
    st.markdown('<div class="gradient-title">🔍 App Tag Auditor</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Automated Firebase Analytics APK Auditing System</div>', unsafe_allow_html=True)

# Initialize session state variables
settings = get_settings()
output_path = settings.LOCAL_OUTPUT_PATH

if "pipeline_completed" not in st.session_state:
    st.session_state["pipeline_completed"] = os.path.exists(output_path)
if "pipeline_running" not in st.session_state:
    st.session_state["pipeline_running"] = False
if "pipeline_error" not in st.session_state:
    st.session_state["pipeline_error"] = None

# Check if pipeline is running
if st.session_state.get("pipeline_running"):
    thread = st.session_state.get("pipeline_thread")
    bridge = st.session_state.get("interaction_bridge")
    log_queue = st.session_state.get("log_queue")
    log_buffer = st.session_state.get("log_buffer", [])
    
    # Check if thread finished
    if thread and not thread.is_alive():
        # Clean up logging handler
        handler = st.session_state.get("streamlit_log_handler")
        old_level = st.session_state.get("old_log_level", logging.INFO)
        if handler:
            logging.getLogger().removeHandler(handler)
            st.session_state["streamlit_log_handler"] = None
        logging.getLogger().setLevel(old_level)
        
        st.session_state["pipeline_running"] = False
        if thread.exception:
            st.session_state["pipeline_completed"] = False
            st.session_state["pipeline_error"] = str(thread.exception)
        else:
            st.session_state["pipeline_completed"] = True
            
        st.rerun()
        
    # Read any new logs
    while log_queue and not log_queue.empty():
        try:
            msg = log_queue.get_nowait()
            log_buffer.append(msg)
        except Exception:
            break
    st.session_state["log_buffer"] = log_buffer
    
    st.markdown('<div class="step-card" style="border-left-color: #7f00c6 !important; background: rgba(127,0,198,0.03) !important;"><h4>⏳ Pipeline Executing</h4><p>The automated audit pipeline is running on the connected Android device. Real-time telemetry logs are displaying below.</p></div>', unsafe_allow_html=True)
    
    # Check for login intervention
    if bridge and bridge.login_detected.is_set():
        is_mid_login = getattr(bridge, 'mid_login_fields', False)

        if is_mid_login:
            # ── Mid-login sub-screen (OTP / verification / next step) ───────
            fields = bridge.discovered_fields or []
            field_labels = ", ".join(f.get("label", f.get("field_type", "Field")) for f in fields) or "required fields"
            st.markdown(f"""
            <div style="background: rgba(100, 100, 255, 0.05); border: 2px solid #7f7fff; border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0; box-shadow: 0 0 20px rgba(127, 127, 255, 0.15);">
                <h3 style="color: #a0a0ff; margin-top: 0;">📲 Verification Step Detected</h3>
                <p style="color: #d8c2e6; font-size: 0.95rem; line-height: 1.5;">
                    The app has moved to the next login step and needs: <strong>{field_labels}</strong>
                </p>
            </div>
            """, unsafe_allow_html=True)

            if not fields:
                fields = [{"label": "OTP / Code", "resource_id": "_fallback_otp", "field_type": "otp"}]

            cred_values = {}
            for i, field in enumerate(fields):
                label = field.get("label") or field.get("field_type", "Field")
                rid = field.get("resource_id", label)
                ftype = field.get("field_type", "text")
                is_password = "password" in ftype.lower() or "password" in label.lower()
                val = st.text_input(
                    label,
                    type="password" if is_password else "default",
                    key=f"mid_cred_input_{i}_{rid}"
                )
                cred_values[rid] = val

            col_sub, col_skip, col_abort = st.columns(3)
            with col_sub:
                if st.button("✅ Submit", use_container_width=True, type="primary", key="btn_mid_submit"):
                    bridge.user_decision = "submit_fields"
                    bridge.credentials = cred_values
                    bridge.user_responded.set()
                    st.rerun()
            with col_skip:
                if st.button("⬅️ Skip Step", use_container_width=True, key="btn_mid_skip"):
                    bridge.user_decision = "skip"
                    bridge.user_responded.set()
                    st.rerun()
            with col_abort:
                if st.button("🛑 Abort", use_container_width=True, key="btn_mid_abort"):
                    bridge.user_decision = "abort"
                    bridge.user_responded.set()
                    st.rerun()

        else:
            # ── First encounter: full choice popup ───────────────────────────
            st.markdown("""
            <div style="background: rgba(255, 143, 0, 0.05); border: 2px solid #ff8f00; border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0; box-shadow: 0 0 20px rgba(255, 143, 0, 0.15);">
                <h3 style="color: #ff8f00; margin-top: 0;">🔑 Login/Signup Screen Detected!</h3>
                <p style="color: #d8c2e6; font-size: 0.95rem; line-height: 1.5;">
                    The crawler is paused at a login or signup screen. Choose how to proceed:
                </p>
            </div>
            """, unsafe_allow_html=True)

            escape_options = bridge.discovered_escape_options or []

            # ── Phase 1: user picks what to do ───────────────────────────────
            if not st.session_state.get("hitl_phase2_active"):

                col_l, col_s = st.columns(2)
                with col_l:
                    if st.button("🔐 Login", use_container_width=True, type="primary", key="btn_hitl_login"):
                        st.session_state["hitl_phase2_active"] = True
                        st.session_state["hitl_phase2_mode"] = "login"
                        st.rerun()
                with col_s:
                    if st.button("📝 Sign Up", use_container_width=True, key="btn_hitl_signup"):
                        st.session_state["hitl_phase2_active"] = True
                        st.session_state["hitl_phase2_mode"] = "signup"
                        st.rerun()

                if escape_options:
                    st.markdown("**Or tap an escape option found on the screen:**")
                    for opt in escape_options:
                        label = opt.get("label", "Unknown")
                        rid = opt.get("resource_id", "")
                        btn_key = f"btn_escape_{rid or label}"
                        if st.button(f"↩️ {label}", use_container_width=True, key=btn_key):
                            bridge.user_decision = f"escape:{rid or label}"
                            bridge.user_responded.set()
                            st.session_state.pop("hitl_phase2_active", None)
                            st.session_state.pop("hitl_phase2_mode", None)
                            st.rerun()

                col_back, col_abort = st.columns(2)
                with col_back:
                    if st.button("⬅️ Go Back", use_container_width=True, key="btn_hitl_skip"):
                        bridge.user_decision = "skip"
                        bridge.user_responded.set()
                        st.session_state.pop("hitl_phase2_active", None)
                        st.session_state.pop("hitl_phase2_mode", None)
                        st.rerun()
                with col_abort:
                    if st.button("🛑 Abort Audit", use_container_width=True, key="btn_hitl_abort"):
                        bridge.user_decision = "abort"
                        bridge.user_responded.set()
                        st.session_state.pop("hitl_phase2_active", None)
                        st.session_state.pop("hitl_phase2_mode", None)
                        st.rerun()

            # ── Phase 2: credential form ──────────────────────────────────────
            else:
                mode = st.session_state.get("hitl_phase2_mode", "login")
                mode_label = "Login" if mode == "login" else "Sign Up"
                fields = bridge.discovered_fields or []

                st.markdown(f"**Enter your {mode_label} credentials:**")

                if not fields:
                    fields = [
                        {"label": "Email / Phone", "resource_id": "_fallback_email", "field_type": "email"},
                        {"label": "Password", "resource_id": "_fallback_password", "field_type": "password"},
                    ]

                cred_values = {}
                for i, field in enumerate(fields):
                    label = field.get("label") or field.get("field_type", "Field")
                    rid = field.get("resource_id", label)
                    ftype = field.get("field_type", "text")
                    is_password = "password" in ftype.lower() or "password" in label.lower()
                    # Include index in key to prevent duplicates when resource_id
                    # is empty or identical across multiple fields.
                    val = st.text_input(
                        label,
                        type="password" if is_password else "default",
                        key=f"cred_input_{i}_{rid}"
                    )
                    cred_values[rid] = val

                col_sub, col_cancel = st.columns(2)
                with col_sub:
                    if st.button(f"✅ Submit & {mode_label}", use_container_width=True, type="primary", key="btn_cred_submit"):
                        bridge.user_decision = mode
                        bridge.credentials = cred_values
                        bridge.user_responded.set()
                        st.session_state.pop("hitl_phase2_active", None)
                        st.session_state.pop("hitl_phase2_mode", None)
                        st.rerun()
                with col_cancel:
                    if st.button("← Back", use_container_width=True, key="btn_cred_back"):
                        st.session_state.pop("hitl_phase2_active", None)
                        st.session_state.pop("hitl_phase2_mode", None)
                        st.rerun()
    
    # Render logs
    st.markdown('<h4 style="color: #ff8f00;">📺 Console Output</h4>', unsafe_allow_html=True)
    st.code("\n".join(log_buffer), language="text")
    
    # Rerun after a delay to poll for updates
    if not (bridge and bridge.login_detected.is_set()):
        time.sleep(0.8)
        st.rerun()
        
    st.stop()

class StreamlitLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            pass

class InteractionBridge:
    def __init__(self):
        self.login_detected = threading.Event()
        self.user_responded = threading.Event()
        # Credential submission round-trip (phase 2)
        self.credentials_needed = threading.Event()
        self.credentials_submitted = threading.Event()
        self.screen_hierarchy = ""
        self.user_decision = None  # 'login', 'signup', 'escape:<label>', 'skip', 'abort'
        # Fields discovered on the login screen: list of {'label': str, 'resource_id': str, 'field_type': str}
        self.discovered_fields: list = []
        # Escape options found on screen: list of {'label': str, 'resource_id': str}
        self.discovered_escape_options: list = []
        # Credentials entered by user: dict mapping resource_id -> value
        self.credentials: dict = {}
        # Set to True after user submits credentials so mid-login screens
        # (OTP, verification, etc.) are not treated as new login prompts
        self.login_in_progress: bool = False
        # Set to True when a mid-login sub-screen (OTP etc.) needs field values
        self.mid_login_fields: bool = False

class PipelineThread(threading.Thread):
    def __init__(self, apk_path, schema_path, interaction_bridge=None):
        super().__init__()
        self.apk_path = apk_path
        self.schema_path = schema_path
        self.interaction_bridge = interaction_bridge
        self.exception = None

    def run(self):
        try:
            run_pipeline(apk_path=self.apk_path, schema_path=self.schema_path, interaction_bridge=self.interaction_bridge)
        except Exception as e:
            self.exception = e

st.markdown('<hr style="border: 0; border-top: 1px solid rgba(255, 255, 255, 0.05); margin: 1.5rem 0;">', unsafe_allow_html=True)

# Two-column layout for file selections
col1, col2 = st.columns(2)

with col1:
    st.markdown('<h3 style="color: #ff8f00;">📁 Target Android APK</h3>', unsafe_allow_html=True)
    apk_source = st.radio("Select APK Source", ["Local Upload", "Google Drive Picker"], key="apk_source")
    
    if apk_source == "Local Upload":
        uploaded_apk = st.file_uploader("Upload APK file", type=["apk"])
        if uploaded_apk is not None:
            settings = get_settings()
            temp_dir = settings.TEMP_STORAGE_DIR
            os.makedirs(temp_dir, exist_ok=True)
            local_apk_path = os.path.join(temp_dir, uploaded_apk.name)
            with open(local_apk_path, "wb") as f:
                f.write(uploaded_apk.getbuffer())
            st.session_state["apk_path"] = local_apk_path
            st.success(f"✅ Loaded Local APK: `{uploaded_apk.name}`")
    else:
        apk_drive = drive_picker.render_drive_picker(
            key="apk",
            label="Pick APK from Google Drive",
            mime_types="application/vnd.android.package-archive",
            token=st.session_state.get("google_auth_token") or ""
        )
        if apk_drive:
            st.info(f"Selected APK from Drive: `{apk_drive['file_name']}`")
            st.session_state["apk_drive"] = apk_drive

with col2:
    st.markdown('<h3 style="color: #ff8f00;">📊 Event Schema Sheet</h3>', unsafe_allow_html=True)
    schema_source = st.radio("Select Schema Source", ["Local Upload", "Google Sheets URL"], key="schema_source")
    
    if schema_source == "Local Upload":
        uploaded_schema = st.file_uploader("Upload Schema file (CSV or Excel)", type=["csv", "xlsx", "xls"])
        if uploaded_schema is not None:
            settings = get_settings()
            temp_dir = settings.TEMP_STORAGE_DIR
            os.makedirs(temp_dir, exist_ok=True)
            local_schema_path = os.path.join(temp_dir, uploaded_schema.name)
            with open(local_schema_path, "wb") as f:
                f.write(uploaded_schema.getbuffer())
            st.session_state["schema_path"] = local_schema_path
            st.success(f"✅ Loaded Local Schema: `{uploaded_schema.name}`")
    else:
        schema_url = st.text_input("Paste Google Sheet URL", value="", key="schema_url")
        token = st.session_state.get("google_auth_token")
        
        if not token:
            token = drive_picker.render_google_auth(
                key="sheet_url_auth",
                label="🔑 Connect Google Account"
            )
            if token:
                st.session_state["google_auth_token"] = token
                st.rerun()
            
        if token:
            if schema_url:
                st.success("✅ Google Account Connected & Sheet URL Ready")
        else:
            if schema_url:
                st.warning("⚠️ Please connect your Google Account using the button above to download the sheet.")

# Run Pipeline Action Section
st.markdown('<hr style="border: 0; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 2rem 0;">', unsafe_allow_html=True)

if st.button("🚀 Run Analytics Audit Pipeline", use_container_width=True):
    # Determine the paths
    apk_path = st.session_state.get("apk_path")
    schema_path = st.session_state.get("schema_path")
    
    # Check if we need to download from Google Drive first
    download_success = True
    temp_dir = get_settings().TEMP_STORAGE_DIR
    os.makedirs(temp_dir, exist_ok=True)
    
    if apk_source == "Google Drive Picker":
        apk_drive = st.session_state.get("apk_drive")
        if not apk_drive:
            st.error("Please pick an APK from Google Drive.")
            download_success = False
        else:
            with st.spinner(f"📥 Downloading APK from Google Drive: {apk_drive['file_name']}..."):
                try:
                    creds = Credentials(token=apk_drive["access_token"])
                    drive_client = DriveClient(credentials=creds)
                    dest_apk_path = os.path.join(temp_dir, apk_drive["file_name"])
                    drive_client.download_file(apk_drive["file_id"], dest_apk_path)
                    apk_path = dest_apk_path
                except Exception as e:
                    st.error(f"Failed to download APK: {e}")
                    download_success = False

    if schema_source == "Google Sheets URL" and download_success:
        schema_url = st.session_state.get("schema_url")
        if not schema_url:
            st.error("Please paste the Google Sheet URL.")
            download_success = False
        else:
            token = st.session_state.get("google_auth_token") or (st.session_state.get("apk_drive") or {}).get("access_token")
            if not token:
                st.error("Google authentication token is missing. Please authorize your Google Account first.")
                download_success = False
            else:
                with st.spinner("📥 Downloading Google Sheet from URL..."):
                    try:
                        sheet_id = SheetsClient.extract_sheet_id_from_url(schema_url)
                        creds = Credentials(token=token)
                        sheets_client = SheetsClient(credentials=creds)
                        dest_sheet_path = os.path.join(temp_dir, f"sheet_{sheet_id}.xlsx")
                        sheets_client.download_sheet_as_excel(sheet_id, dest_sheet_path)
                        schema_path = dest_sheet_path
                    except Exception as e:
                        st.error(f"Failed to download Google Sheet: {e}")
                        download_success = False

    if not apk_path:
        st.error("Missing target APK file.")
        download_success = False
    if not schema_path:
        st.error("Missing event schema file.")
        download_success = False

    if download_success:
        # Setup logging redirection to Streamlit UI via queue
        log_queue = queue.Queue()
        root_logger = logging.getLogger()
        handler = StreamlitLogHandler(log_queue)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        
        st.session_state["pipeline_completed"] = False
        st.session_state["pipeline_error"] = None
        st.session_state["log_queue"] = log_queue
        st.session_state["log_buffer"] = []
        st.session_state["streamlit_log_handler"] = handler
        st.session_state["old_log_level"] = old_level
        
        # Start pipeline execution in background thread with InteractionBridge
        bridge = InteractionBridge()
        st.session_state["interaction_bridge"] = bridge
        
        thread = PipelineThread(apk_path=apk_path, schema_path=schema_path, interaction_bridge=bridge)
        thread.start()
        st.session_state["pipeline_thread"] = thread
        st.session_state["pipeline_running"] = True
        st.rerun()

# Display final results if they exist and pipeline was completed successfully in this session
settings = get_settings()
output_path = settings.LOCAL_OUTPUT_PATH

if st.session_state.get("pipeline_error"):
    st.error(f"❌ Pipeline execution failed: {st.session_state['pipeline_error']}")

if st.session_state.get("pipeline_completed") and os.path.exists(output_path):
    st.markdown('<hr style="border: 0; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 2rem 0;">', unsafe_allow_html=True)
    st.markdown('<h3 style="color: #ff8f00;">📊 Audit Results Report</h3>', unsafe_allow_html=True)
    
    # Determine the output download filename dynamically based on the input schema name
    schema_source = st.session_state.get("schema_source")
    given_sheet_name = "results"
    if schema_source == "Google Sheets URL":
        schema_url = st.session_state.get("schema_url")
        if schema_url:
            given_sheet_name = SheetsClient.extract_sheet_id_from_url(schema_url)
    else:
        schema_path = st.session_state.get("schema_path")
        if schema_path:
            given_sheet_name = os.path.splitext(os.path.basename(schema_path))[0]
            
    export_filename = f"audit_result_{given_sheet_name}.xlsx"

    with open(output_path, "rb") as f:
        st.download_button(
            label="📥 Download Generated Excel Report",
            data=f,
            file_name=export_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # Let's read and display the tabs from output excel file
    try:
        xl = pd.ExcelFile(output_path)
        sheet_names = xl.sheet_names
        
        # Sort sheet names so Audit Summary and Audit Analysis are shown first
        preferred_order = ["Audit Summary", "Audit Analysis"]
        sorted_sheet_names = [s for s in preferred_order if s in sheet_names] + [s for s in sheet_names if s not in preferred_order]
        
        # Hidden text area for React-based WebSocket updates (prevents page reloads)
        st.markdown("""
        <style>
        div.hidden-text-area {
            display: none !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="hidden-text-area">', unsafe_allow_html=True)
            edit_data_json = st.text_area("hidden_edit_data_widget", key="hidden_edit_data_widget", value="")
            st.markdown('</div>', unsafe_allow_html=True)
            
        if edit_data_json:
            try:
                import json
                import openpyxl
                from openpyxl.styles import PatternFill, Font
                
                data = json.loads(edit_data_json)
                active_sheet = data.get("sheet")
                rows = data.get("rows", {})
                
                wb = openpyxl.load_workbook(output_path)
                if active_sheet in wb.sheetnames:
                    ws = wb[active_sheet]
                    headers = [cell.value for cell in ws[1]]
                    status_col_idx = headers.index("Status") + 1
                    comments_col_idx = headers.index("Comments") + 1
                    logs_col_idx = headers.index("Logs") + 1
                    
                    font_family = "Segoe UI"
                    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
                    green_font = Font(name=font_family, size=10, bold=True, color="375623")
                    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                    yellow_font = Font(name=font_family, size=10, bold=True, color="7F6000")
                    red_fill = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid")
                    red_font = Font(name=font_family, size=10, bold=True, color="78281F")
                    gray_fill = PatternFill(start_color="EAECEE", end_color="EAECEE", fill_type="solid")
                    gray_font = Font(name=font_family, size=10, bold=True, color="5D6D7E")
                    
                    for row_str, changes in rows.items():
                        row_idx = int(row_str)
                        excel_row = row_idx + 2
                        
                        if "status" in changes:
                            val = changes["status"]
                            cell = ws.cell(row=excel_row, column=status_col_idx, value=val)
                            if val == "Implemented":
                                cell.fill = green_fill
                                cell.font = green_font
                            elif val == "Implemented with issues":
                                cell.fill = yellow_fill
                                cell.font = yellow_font
                            elif val == "Scenario Not Found":
                                cell.fill = gray_fill
                                cell.font = gray_font
                            else:
                                cell.fill = red_fill
                                cell.font = red_font
                                
                        if "comments" in changes:
                            ws.cell(row=excel_row, column=comments_col_idx, value=changes["comments"])
                            
                        if "logs" in changes:
                            ws.cell(row=excel_row, column=logs_col_idx, value=changes["logs"])
                    
                    # Recalculate summary tab counts
                    if "Audit Summary" in wb.sheetnames:
                        ws_summary = wb["Audit Summary"]
                        implemented_count = 0
                        implemented_with_issues_count = 0
                        not_implemented_count = 0
                        scenario_not_found_count = 0
                        
                        for r in range(2, ws.max_row + 1):
                            val = ws.cell(row=r, column=status_col_idx).value
                            if val == "Implemented":
                                implemented_count += 1
                            elif val == "Implemented with issues":
                                implemented_with_issues_count += 1
                            elif val == "Scenario Not Found":
                                scenario_not_found_count += 1
                            else:
                                not_implemented_count += 1
                                
                        ws_summary["B5"] = implemented_count
                        ws_summary["B6"] = implemented_with_issues_count
                        ws_summary["B7"] = not_implemented_count
                        ws_summary["B8"] = scenario_not_found_count
                        
                    wb.save(output_path)
                    st.success("💾 Changes saved successfully! Downloading updated report...")
                    
                    import base64
                    with open(output_path, "rb") as f_excel:
                        b64_data = base64.b64encode(f_excel.read()).decode()
                        
                    st.markdown(f"""
                    <a id="auto_download_link" download="{export_filename}" href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_data}"></a>
                    <script>
                        setTimeout(() => {{
                            const link = parent.document.getElementById("auto_download_link") || document.getElementById("auto_download_link");
                            if (link) {{
                                link.click();
                            }}
                        }}, 300);
                    </script>
                    """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error saving edits: {e}")
                
            st.session_state["hidden_edit_data_widget"] = ""

        # Sort sheet names so Audit Summary and Audit Analysis are shown first
        preferred_order = ["Audit Summary", "Audit Analysis"]
        sorted_sheet_names = [s for s in preferred_order if s in sheet_names] + [s for s in sheet_names if s not in preferred_order]
        
        def render_html_table(df, is_summary=False, sheet_name=""):
            # Clean up nan values for proper display
            df = df.fillna("")
            
            def get_status_badge(val):
                val_clean = str(val).strip()
                if val_clean == "Implemented":
                    return '<span style="background-color: #E2EFDA; color: #375623; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.85rem; display: inline-block;">Implemented</span>'
                elif val_clean == "Implemented with issues":
                    return '<span style="background-color: #FFF2CC; color: #7F6000; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.85rem; display: inline-block;">Implemented with issues</span>'
                elif val_clean == "Scenario Not Found":
                    return '<span style="background-color: #EAECEE; color: #5D6D7E; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.85rem; display: inline-block;">Scenario Not Found</span>'
                elif val_clean == "Not Implemented":
                    return '<span style="background-color: #FADBD8; color: #78281F; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.85rem; display: inline-block;">Not Implemented</span>'
                return val_clean

            # Build HTML table
            html = '<style>'
            html += ' .audit-btn { background: linear-gradient(135deg, #ff8f00 0%, #ffb300 100%); color: #0f111a; border: none; padding: 12px 28px; border-radius: 8px; font-weight: bold; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 12px rgba(255,143,0,0.25); transition: all 0.2s ease; }'
            html += ' .audit-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(255,143,0,0.35); }'
            html += ' .audit-btn:active { transform: translateY(0); }'
            html += ' .audit-select { background-color: #1a1f2c; color: #e5e7eb; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; padding: 6px 12px; font-family: inherit; font-size: 0.85rem; font-weight: bold; width: 100%; cursor: pointer; transition: border-color 0.2s; }'
            html += ' .audit-select:focus { border-color: #ff8f00; outline: none; }'
            html += ' .audit-textarea { background-color: #1a1f2c; color: #e5e7eb; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; padding: 8px 12px; font-family: inherit; font-size: 0.85rem; width: 100%; resize: vertical; box-sizing: border-box; transition: border-color 0.2s; }'
            html += ' .audit-textarea:focus { border-color: #ff8f00; outline: none; }'
            html += ' .audit-logs-textarea { background-color: #1a1f2c; color: #d1d5db; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; padding: 8px 12px; font-family: monospace; font-size: 0.8rem; width: 100%; resize: vertical; box-sizing: border-box; line-height: 1.4; transition: border-color 0.2s; }'
            html += ' .audit-logs-textarea:focus { border-color: #ff8f00; outline: none; }'
            html += '</style>'
            
            # Inject saveAuditEdits JS globally
            html += """
<script>
if (typeof window.saveAuditEdits === 'undefined') {
    window.saveAuditEdits = function(sheetName) {
        const container = document.querySelector(`.audit-edit-container[data-sheet="${sheetName}"]`);
        if (!container) return;
        
        const edits = {
            sheet: sheetName,
            rows: {}
        };
        
        container.querySelectorAll('select[name^="status_"]').forEach(el => {
            const rowIdx = el.name.split('_')[1];
            if (!edits.rows[rowIdx]) edits.rows[rowIdx] = {};
            edits.rows[rowIdx].status = el.value;
        });
        
        container.querySelectorAll('textarea[name^="comments_"]').forEach(el => {
            const rowIdx = el.name.split('_')[1];
            if (!edits.rows[rowIdx]) edits.rows[rowIdx] = {};
            edits.rows[rowIdx].comments = el.value;
        });
        
        container.querySelectorAll('textarea[name^="logs_"]').forEach(el => {
            const rowIdx = el.name.split('_')[1];
            if (!edits.rows[rowIdx]) edits.rows[rowIdx] = {};
            edits.rows[rowIdx].logs = el.value;
        });
        
        // Find Streamlit hidden textarea in parent / main document
        const textarea = parent.document.querySelector('div.hidden-text-area textarea') || document.querySelector('div.hidden-text-area textarea');
        if (!textarea) {
            console.error("Streamlit hidden communication textarea not found.");
            return;
        }
        
        // React-compatible value setting
        const lastValue = textarea.value;
        textarea.value = JSON.stringify(edits);
        const event = new Event('input', { bubbles: true });
        event.simulated = true;
        const tracker = textarea._valueTracker;
        if (tracker) {
            tracker.setValue(lastValue);
        }
        textarea.dispatchEvent(event);
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.blur();
    };
}
</script>
"""
            
            if not is_summary:
                html += f'<form onsubmit="event.preventDefault(); saveAuditEdits(\'{sheet_name}\');" class="audit-edit-container" data-sheet="{sheet_name}">'

            html += '<div style="overflow-x: auto; margin: 1rem 0; width: 100%; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">'
            html += '<table style="width: 100%; border-collapse: collapse; background-color: #161a24; font-size: 0.9rem;">'
            
            # Table Headers
            html += '<thead><tr style="background-color: #1f2430; border-bottom: 2px solid rgba(255,255,255,0.1);">'
            for col in df.columns:
                th_style = 'padding: 12px 16px; text-align: left; font-weight: 600; color: #ff8f00; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap;'
                if col == "Logs":
                    th_style += ' min-width: 450px;'
                elif col == "Event Parameters Example Values":
                    th_style += ' min-width: 220px;'
                elif col == "Comments":
                    th_style += ' min-width: 300px;'
                elif col == "Principle":
                    th_style += ' min-width: 250px;'
                elif col in ["Status", "Static Status Category"]:
                    th_style += ' min-width: 220px;'
                html += f'<th style="{th_style}">{col}</th>'
            html += '</tr></thead>'
            
            # Table Body
            html += '<tbody>'
            for row_idx, row in df.iterrows():
                html += '<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">'
                for col in df.columns:
                    val = row[col]
                    val_str = str(val).strip()
                    
                    if is_summary:
                        if col == "Static Status Category":
                            cell_content = get_status_badge(val_str)
                        else:
                            if col in ["Comments", "Logs"] and val_str:
                                formatted_val = val_str.replace("\n", "<br/>")
                                max_w = "800px" if col == "Logs" else "600px"
                                cell_content = f'<div style="white-space: pre-wrap; font-family: monospace; font-size: 0.8rem; line-height: 1.4; color: #d1d5db; max-width: {max_w}; word-break: break-all;">{formatted_val}</div>'
                            elif val_str:
                                cell_content = f'<div style="white-space: pre-wrap; color: #e5e7eb; word-break: break-word;">{val_str}</div>'
                            else:
                                cell_content = '<span style="color: #6b7280; font-style: italic;">None</span>'
                    else:
                        # Editable controls for Status, Comments, Logs
                        if col == "Status":
                            status_options = ["Implemented", "Implemented with issues", "Scenario Not Found", "Not Implemented"]
                            select_html = f'<select name="status_{row_idx}" class="audit-select">'
                            for opt in status_options:
                                selected = "selected" if val_str == opt else ""
                                select_html += f'<option value="{opt}" {selected}>{opt}</option>'
                            select_html += '</select>'
                            cell_content = select_html
                        elif col == "Comments":
                            cell_content = f'<textarea name="comments_{row_idx}" class="audit-textarea" style="height: 60px;">{val_str}</textarea>'
                        elif col == "Logs":
                            lines_count = val_str.count("\n") + 1
                            h_px = max(60, min(300, lines_count * 18))
                            cell_content = f'<textarea name="logs_{row_idx}" class="audit-logs-textarea" style="height: {h_px}px;">{val_str}</textarea>'
                        else:
                            if val_str:
                                cell_content = f'<div style="white-space: pre-wrap; color: #e5e7eb; word-break: break-word;">{val_str}</div>'
                            else:
                                cell_content = '<span style="color: #6b7280; font-style: italic;">None</span>'
                    
                    td_style = 'padding: 12px 16px; vertical-align: top;'
                    if col == "Logs":
                        td_style += ' min-width: 450px;'
                    elif col == "Event Parameters Example Values":
                        td_style += ' min-width: 220px;'
                    elif col == "Comments":
                        td_style += ' min-width: 300px;'
                    elif col == "Principle":
                        td_style += ' min-width: 250px;'
                    elif col in ["Status", "Static Status Category"]:
                        td_style += ' min-width: 220px;'
                    html += f'<td style="{td_style}">{cell_content}</td>'
                html += '</tr>'
            html += '</tbody></table></div>'
            
            if not is_summary:
                html += '<div style="margin: 1.5rem 0; text-align: right;">'
                html += '<button type="submit" class="audit-btn">💾 Save Changes to Excel</button>'
                html += '</div>'
                html += '</form>'
                
            st.html(html)

        tabs = st.tabs(sorted_sheet_names)
        for i, sheet_name in enumerate(sorted_sheet_names):
            with tabs[i]:
                if sheet_name == "Audit Summary":
                    try:
                        df = pd.read_excel(output_path, sheet_name=sheet_name, header=3)
                        df = df.dropna(how="all")
                        st.markdown("#### 📊 App Tag Auditor - Audit Summary")
                        render_html_table(df, is_summary=True)
                    except Exception as e:
                        df = pd.read_excel(output_path, sheet_name=sheet_name)
                        render_html_table(df, is_summary=True)
                else:
                    df = pd.read_excel(output_path, sheet_name=sheet_name)
                    df = df.fillna("")
                    st.markdown("##### 🔍 Audit Analysis & Verification")
                    render_html_table(df, is_summary=False, sheet_name=sheet_name)
    except Exception as e:
        st.warning(f"Could not load preview table for the Excel sheet: {e}")
