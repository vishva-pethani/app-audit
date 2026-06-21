import sys
import os
import streamlit as st
import pandas as pd
import logging
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
    if name.startswith("core") or name.startswith("agents") or name == "orchestrator"
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
from frontend.components.drive_picker import render_drive_picker
from orchestrator import run_pipeline

st.set_page_config(
    page_title="App Tag Auditor",
    page_icon="🔍",
    layout="wide",
)

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

# Main Title Section
st.markdown('<div class="gradient-title">🔍 App Tag Auditor</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Automated Firebase Analytics APK Auditing System</div>', unsafe_allow_html=True)

class StreamlitLogHandler(logging.Handler):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.log_buffer = []

    def emit(self, record):
        msg = self.format(record)
        self.log_buffer.append(msg)
        try:
            self.placeholder.code("\n".join(self.log_buffer))
        except Exception:
            pass

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
            mime_types="application/vnd.android.package-archive"
        )
        if apk_drive:
            st.info(f"Selected APK from Drive: `{apk_drive['file_name']}`")
            st.session_state["apk_drive"] = apk_drive

with col2:
    st.markdown('<h3 style="color: #ff8f00;">📊 Event Schema Sheet</h3>', unsafe_allow_html=True)
    schema_source = st.radio("Select Schema Source", ["Local Upload", "Google Drive Sheets Picker"], key="schema_source")
    
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
        sheet_drive = render_drive_picker(
            key="sheet",
            label="Pick Google Sheet from Drive",
            mime_types="application/vnd.google-apps.spreadsheet"
        )
        if sheet_drive:
            st.info(f"Selected Sheet from Drive: `{sheet_drive['file_name']}`")
            st.session_state["sheet_drive"] = sheet_drive

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

    if schema_source == "Google Drive Sheets Picker" and download_success:
        sheet_drive = st.session_state.get("sheet_drive")
        if not sheet_drive:
            st.error("Please pick a Google Sheet from Drive.")
            download_success = False
        else:
            with st.spinner(f"📥 Downloading Google Sheet from Drive: {sheet_drive['file_name']}..."):
                try:
                    creds = Credentials(token=sheet_drive["access_token"])
                    sheets_client = SheetsClient(credentials=creds)
                    dest_sheet_path = os.path.join(temp_dir, f"{sheet_drive['file_name']}.xlsx")
                    sheets_client.download_sheet_as_excel(sheet_drive["file_id"], dest_sheet_path)
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
        st.info("Pipeline execution starting. Real-time console logs will display below:")
        
        # Setup logging redirection to Streamlit UI
        root_logger = logging.getLogger()
        log_placeholder = st.empty()
        handler = StreamlitLogHandler(log_placeholder)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        
        try:
            run_pipeline(apk_path=apk_path, schema_path=schema_path)
            st.success("🎉 Audit pipeline completed successfully!")
        except Exception as e:
            st.error(f"❌ Pipeline execution failed: {e}")
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(old_level)

# Display final results if they exist
settings = get_settings()
output_path = settings.LOCAL_OUTPUT_PATH

if os.path.exists(output_path):
    st.markdown('<hr style="border: 0; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 2rem 0;">', unsafe_allow_html=True)
    st.markdown('<h3 style="color: #ff8f00;">📊 Audit Results Report</h3>', unsafe_allow_html=True)
    
    with open(output_path, "rb") as f:
        st.download_button(
            label="📥 Download Generated Excel Report",
            data=f,
            file_name="audit_results.xlsx",
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
        
        def style_status(val):
            if val == "Implemented":
                return "background-color: #E2EFDA; color: #375623; font-weight: bold;"
            elif val == "Implemented with issues":
                return "background-color: #FFF2CC; color: #7F6000; font-weight: bold;"
            elif val == "Not Implemented":
                return "background-color: #FADBD8; color: #78281F; font-weight: bold;"
            return ""

        tabs = st.tabs(sorted_sheet_names)
        for i, sheet_name in enumerate(sorted_sheet_names):
            with tabs[i]:
                if sheet_name == "Audit Summary":
                    try:
                        df = pd.read_excel(output_path, sheet_name=sheet_name, header=3)
                        df = df.dropna(how="all")
                        st.markdown("#### 📊 App Tag Auditor - Audit Summary")
                        if hasattr(df.style, "map"):
                            styled_df = df.style.map(style_status, subset=["Static Status Category"])
                        else:
                            styled_df = df.style.applymap(style_status, subset=["Static Status Category"])
                        st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    except Exception as e:
                        df = pd.read_excel(output_path, sheet_name=sheet_name)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    df = pd.read_excel(output_path, sheet_name=sheet_name)
                    if "Status" in df.columns:
                        if hasattr(df.style, "map"):
                            styled_df = df.style.map(style_status, subset=["Status"])
                        else:
                            styled_df = df.style.applymap(style_status, subset=["Status"])
                        st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"Could not load preview table for the Excel sheet: {e}")
