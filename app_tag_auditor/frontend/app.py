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
from frontend.components.drive_picker import render_drive_picker, render_google_auth
from orchestrator import run_pipeline

st.set_page_config(
    page_title="App Tag Auditor",
    page_icon="🔍",
    layout="wide",
)

settings = get_settings()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "google_auth_token" not in st.session_state:
    st.session_state["google_auth_token"] = None
if "user_profile" not in st.session_state:
    st.session_state["user_profile"] = None

# Check query parameters for incoming Google Access Token
query_params = st.query_params
if "google_auth_access_token" in query_params:
    access_token = query_params["google_auth_access_token"]
    try:
        import requests
        res = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        if res.status_code == 200:
            profile = res.json()
            st.session_state["authenticated"] = True
            st.session_state["google_auth_token"] = access_token
            st.session_state["user_profile"] = profile
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Google authentication token verification failed. Please try again.")
    except Exception as e:
        st.error(f"Error authenticating with Google: {e}")

# If NOT authenticated, show the login guard page and stop execution!
if not st.session_state["authenticated"]:
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    
    # Check if client ID is configured properly
    client_id_error_html = ""
    button_disabled_attr = ""
    if not client_id or client_id == "your-google-oauth-client-id.apps.googleusercontent.com":
        client_id_error_html = """
        <div style="color: #ff4b4b; font-size: 0.95rem; font-weight: 600; padding: 1rem; background: rgba(255, 75, 75, 0.08); border: 1px solid rgba(255, 75, 75, 0.2); border-radius: 12px; width: 100%; margin-top: 1rem;">
            ⚠️ Google Client ID is not configured. Please check your .env file.
        </div>
        """
        button_disabled_attr = "disabled"

    login_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>🤖 App Tag Auditor — Sign In</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://accounts.google.com/gsi/client" async defer></script>
    <style>
        :root {{
            --bg-color: #0c0f17;
            --panel-bg: rgba(22, 28, 45, 0.45);
            --panel-border: rgba(255, 255, 255, 0.08);
            --text-primary: #ffffff;
            --text-secondary: #8892b0;
            --accent: #ff4b4b;
            --font-main: 'Outfit', sans-serif;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            transition: all 0.25s ease;
        }}

        body {{
            background: var(--bg-color);
            color: var(--text-primary);
            font-family: var(--font-main);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
            position: relative;
        }}

        .ambient-glow-1 {{
            position: absolute;
            width: 500px;
            height: 500px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(255, 75, 75, 0.15) 0%, rgba(0,0,0,0) 70%);
            top: -150px;
            left: -150px;
            filter: blur(80px);
            z-index: 1;
        }}

        .ambient-glow-2 {{
            position: absolute;
            width: 600px;
            height: 600px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(255, 143, 0, 0.12) 0%, rgba(0,0,0,0) 70%);
            bottom: -200px;
            right: -150px;
            filter: blur(90px);
            z-index: 1;
        }}

        .login-card {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 28px;
            padding: 3.5rem 2.5rem;
            width: 100%;
            max-width: 450px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            z-index: 10;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2rem;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        header h1 {{
            font-size: 2.3rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin-bottom: 0.75rem;
            background: linear-gradient(135deg, #ffffff 40%, #8892b0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        header p {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.6;
            max-width: 320px;
            margin: 0 auto;
        }}

        .google-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            background: #0f141c;
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 99px;
            padding: 14px 28px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            transition: all 0.2s ease;
            outline: none;
            font-family: var(--font-main);
        }}

        .google-btn:hover:not(:disabled) {{
            background: #ff4b4b;
            border-color: #ff4b4b;
            box-shadow: 0 4px 20px rgba(255, 75, 75, 0.4);
            transform: translateY(-1px);
        }}

        .google-btn:active:not(:disabled) {{
            transform: translateY(1px);
        }}

        .google-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .google-icon-wrapper {{
            display: flex;
            align-items: center;
            justify-content: center;
            background: white;
            border-radius: 50%;
            width: 24px;
            height: 24px;
        }}
    </style>
</head>
<body>
    <div class="ambient-glow-1"></div>
    <div class="ambient-glow-2"></div>

    <div class="login-card">
        <header>
            <h1 style="display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                <svg viewBox="0 0 24 24" width="38" height="38" fill="rgba(255, 75, 75, 0.15)" stroke="#ff4b4b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block; filter: drop-shadow(0 0 12px rgba(255, 75, 75, 0.45));">
                    <rect x="3" y="11" width="18" height="10" rx="2"></rect>
                    <circle cx="12" cy="5" r="2"></circle>
                    <path d="M12 7v4"></path>
                    <line x1="8" y1="16" x2="8" y2="16"></line>
                    <line x1="16" y1="16" x2="16" y2="16"></line>
                </svg>
                App Tag Auditor
            </h1>
            <p style="margin-top: 1.5rem;">Please sign in with your Google account to access the auditing dashboard.</p>
        </header>

        <button id="login-button" onclick="login()" {button_disabled_attr} class="google-btn">
            <span class="google-icon-wrapper">
                <svg class="google-icon" viewBox="0 0 24 24" width="16" height="16">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22c-.14-.42-.23-.88-.23-1.37z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
            </span>
            Sign in with Google
        </button>

        {client_id_error_html}
    </div>

    <script>
        let tokenClient;
        
        function initClient() {{
            tokenClient = google.accounts.oauth2.initTokenClient({{
                client_id: '{client_id}',
                scope: 'https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets',
                callback: (tokenResponse) => {{
                    if (tokenResponse && tokenResponse.access_token) {{
                        const currentUrl = new URL(window.top.location.href);
                        currentUrl.searchParams.set('google_auth_access_token', tokenResponse.access_token);
                        window.top.location.href = currentUrl.toString();
                    }} else {{
                        alert("Sign-in failed. Please try again.");
                    }}
                }}
            }});
        }}

        window.onload = function() {{
            let gsiInterval = setInterval(() => {{
                if (typeof google !== 'undefined' && google.accounts && google.accounts.oauth2) {{
                    clearInterval(gsiInterval);
                    initClient();
                    if ('{client_id}' && '{client_id}' !== 'your-google-oauth-client-id.apps.googleusercontent.com') {{
                        document.getElementById("login-button").disabled = false;
                    }}
                }}
            }}, 100);
        }};

        function login() {{
            if (tokenClient) {{
                tokenClient.requestAccessToken({{ prompt: 'consent' }});
            }}
        }}
    </script>
</body>
</html>
"""
    # Render full viewport login component
    import streamlit.components.v1 as components
    components.html(login_html, height=750)
    st.stop()

# Custom premium styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif;
}

/* Base custom design / background styling */
.main {
    background: linear-gradient(135deg, #0e1117 0%, #161a24 100%);
    color: #ffffff;
}

/* Glassmorphism card container */
.glass-container {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 16px;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px rgba(255, 255, 255, 0.08) solid;
    padding: 2.5rem;
    margin: 2rem 0;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
}

/* Gradient text */
.gradient-title {
    background: linear-gradient(45deg, #ff4b4b, #ff8f00);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 3rem;
    margin-bottom: 0.5rem;
}

.sub-title {
    color: #8892b0;
    font-size: 1.2rem;
    margin-bottom: 2rem;
}

.step-card {
    background: rgba(255, 255, 255, 0.02);
    border-left: 4px solid #ff4b4b;
    border-radius: 4px;
    padding: 1rem;
    margin-bottom: 1rem;
}

.step-card h4 {
    margin-top: 0;
    color: #ff8f00;
}
</style>
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
            <div style="display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 15px; margin-bottom: 5px;">
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
            # Clear all selection & auth states
            for k in list(st.session_state.keys()):
                if k.startswith("google_auth_token_") or k.startswith("drive_selection_"):
                    del st.session_state[k]
            if "apk_drive" in st.session_state:
                del st.session_state["apk_drive"]
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

class PipelineThread(threading.Thread):
    def __init__(self, apk_path, schema_path):
        super().__init__()
        self.apk_path = apk_path
        self.schema_path = schema_path
        self.exception = None

    def run(self):
        try:
            run_pipeline(apk_path=self.apk_path, schema_path=self.schema_path)
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
        apk_drive = render_drive_picker(
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
            token = render_google_auth(
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
        info_placeholder = st.empty()
        info_placeholder.info("Pipeline execution starting. Real-time console logs will display below:")
        
        # Setup logging redirection to Streamlit UI via queue
        log_queue = queue.Queue()
        root_logger = logging.getLogger()
        log_placeholder = st.empty()
        handler = StreamlitLogHandler(log_queue)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        
        st.session_state["pipeline_completed"] = False
        st.session_state["pipeline_error"] = None
        
        # Start pipeline execution in background thread
        thread = PipelineThread(apk_path=apk_path, schema_path=schema_path)
        thread.start()
        
        log_buffer = []
        try:
            while thread.is_alive():
                updated = False
                while not log_queue.empty():
                    try:
                        msg = log_queue.get_nowait()
                        log_buffer.append(msg)
                        updated = True
                    except queue.Empty:
                        break
                if updated:
                    log_placeholder.code("\n".join(log_buffer))
                time.sleep(0.2)
                
            # Process remaining logs
            while not log_queue.empty():
                try:
                    msg = log_queue.get_nowait()
                    log_buffer.append(msg)
                except queue.Empty:
                    break
            log_placeholder.code("\n".join(log_buffer))
            
            # Check if thread succeeded or failed
            if thread.exception:
                raise thread.exception
                
            st.session_state["pipeline_completed"] = True
            st.success("🎉 Audit pipeline completed successfully!")
            log_placeholder.empty()
            info_placeholder.empty()
        except Exception as e:
            st.session_state["pipeline_completed"] = False
            st.session_state["pipeline_error"] = str(e)
            st.error(f"❌ Pipeline execution failed: {e}")
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(old_level)

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
        
        # Process inline form edits from query params
        params = st.query_params
        if params.get("action") == "save_audit":
            active_sheet = params.get("active_sheet", "Audit Analysis")
            try:
                import openpyxl
                from openpyxl.styles import PatternFill, Font
                import collections
                
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
                    
                    edits = collections.defaultdict(dict)
                    for k, v in params.items():
                        if k.startswith("status_"):
                            row_idx = int(k.split("_")[1])
                            edits[row_idx]["Status"] = v
                        elif k.startswith("comments_"):
                            row_idx = int(k.split("_")[1])
                            edits[row_idx]["Comments"] = v
                        elif k.startswith("logs_"):
                            row_idx = int(k.split("_")[1])
                            edits[row_idx]["Logs"] = v
                    
                    for row_idx, changes in edits.items():
                        excel_row = row_idx + 2
                        
                        if "Status" in changes:
                            val = changes["Status"]
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
                                
                        if "Comments" in changes:
                            ws.cell(row=excel_row, column=comments_col_idx, value=changes["Comments"])
                            
                        if "Logs" in changes:
                            ws.cell(row=excel_row, column=logs_col_idx, value=changes["Logs"])
                    
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
                    st.success("Changes saved successfully!")
            except Exception as e:
                st.error(f"Error saving edits: {e}")
                
            st.query_params.clear()
            st.rerun()

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
            
            if not is_summary:
                html += f'<form action="" method="GET">'
                html += f'<input type="hidden" name="action" value="save_audit">'
                html += f'<input type="hidden" name="active_sheet" value="{sheet_name}">'

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
