import sys
import os
import streamlit as st

# Ensure the app_tag_auditor directory is in sys.path so core and frontend imports resolve correctly
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from frontend.components.drive_picker import render_drive_picker

st.set_page_config(
    page_title="App Tag Auditor - Scaffolding",
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

# Google Drive Picker Integration for testing
st.markdown('<h3 style="color: #ff8f00;">📁 Select Target APK</h3>', unsafe_allow_html=True)
drive_selection = render_drive_picker()
if drive_selection:
    masked_selection = {
        "file_id": drive_selection["file_id"],
        "file_name": drive_selection["file_name"],
        "access_token": f"•••••••• (length: {len(drive_selection['access_token'])})"
    }
    st.success(f"✅ Selected: {drive_selection['file_name']}")
    st.json(masked_selection)

# Card displaying current stage details
st.markdown("""
<div class="glass-container">
    <h2>🛠️ Scaffolding In Progress</h2>
    <p style="font-size: 1.1rem; line-height: 1.6; color: #cbd5e1;">
        Scaffolding in progress — see Prompt 2 for Drive picker, Prompt 3 for full UI.
    </p>
    <p style="font-size: 1.1rem; line-height: 1.6; color: #cbd5e1;">
        The system scaffold has been successfully initialized. The directory structure, core validation models, 
        Google Drive/Sheets API integration clients, and agent stubs are ready for subsequent phases of implementation.
    </p>
    <hr style="border: 0; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 2rem 0;">
    <h3 style="color: #ff8f00;">Next Milestones</h3>
    <div class="step-card">
        <h4>🔗 Phase 2: Drive Picker & Authentication</h4>
        <p>Integrate client-side OAuth authentication using Google Identity Services (GIS) and Drive Picker to select the target APK.</p>
    </div>
    <div class="step-card">
        <h4>🤖 Phase 3: Agent Orchestration & Interactive UI</h4>
        <p>Implement smali code mapping, Appium crawl coordination, logcat validation engine, and full dashboard integration.</p>
    </div>
</div>
""", unsafe_allow_html=True)
