import streamlit as st
import streamlit.components.v1 as components
from core.config import get_settings
from google.oauth2.credentials import Credentials
from core.drive_client import DriveClient
import os

def select_file_callback(file_id, file_name, key):
    st.session_state[f"temp_selected_file_id_{key}"] = file_id
    st.session_state[f"temp_selected_file_name_{key}"] = file_name

def refresh_callback(key):
    st.session_state.pop(f"all_drive_files_{key}", None)

@st.dialog("Select a file", width="large")
def drive_picker_dialog(mime_types: str, key: str):
    """
    Renders the Google Drive Picker modal dialog.
    """
    token = st.session_state.get("google_auth_token")
    if not token:
        st.error("Authentication token is missing. Please sign in again.")
        if st.button("Close"):
            st.rerun()
        return

    # Inject custom stylesheet globally via non-indented st.markdown
    st.markdown("""
<style>
.stTabs [data-baseweb="tab-list"] {
    gap: 24px !important;
    border-bottom: 1px solid rgba(128, 128, 128, 0.15) !important;
}
.stTabs [data-baseweb="tab"] {
    height: 44px !important;
    white-space: pre-wrap !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    color: var(--text-color) !important;
    opacity: 0.6 !important;
    background: transparent !important;
    border: none !important;
}
.stTabs [aria-selected="true"] {
    color: #ff8f00 !important;
    opacity: 1.0 !important;
    border-bottom: 2px solid #ff8f00 !important;
}

.drive-card {
    background-color: var(--secondary-background-color) !important;
    border: 1px solid rgba(128, 128, 128, 0.15) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    text-align: center !important;
    height: 160px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    transition: all 0.2s ease !important;
}
.drive-card:hover {
    background-color: var(--background-color) !important;
    border-color: #ef4444 !important;
}
.drive-card-selected {
    background-color: rgba(255, 143, 0, 0.12) !important;
    border: 2px solid #ff8f00 !important;
    box-shadow: 0 0 16px rgba(255, 143, 0, 0.3) !important;
}
.drive-card-title {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    color: var(--text-color) !important;
    text-overflow: ellipsis !important;
    overflow: hidden !important;
    width: 100% !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    line-height: 1.3 !important;
    margin-top: 8px !important;
}
</style>
""", unsafe_allow_html=True)

    tab_drive, tab_upload = st.tabs(["Google Drive", "Upload"])

    with tab_drive:
        # Search & Refresh Row
        col_search_input, col_refresh_btn = st.columns([5, 1])
        search_query = col_search_input.text_input(
            "Search files", 
            label_visibility="collapsed", 
            placeholder="Type file name to search..."
        )
        col_refresh_btn.button(
            "🔄 Refresh", 
            use_container_width=True, 
            key=f"ref_btn_{key}",
            on_click=refresh_callback,
            args=(key,)
        )

        # Load files into session state if not cached
        if f"all_drive_files_{key}" not in st.session_state:
            try:
                creds = Credentials(token=token)
                drive_client = DriveClient(credentials=creds)
                
                # Query setup
                q = "trashed = false"
                if mime_types:
                    mimes = [m.strip() for m in mime_types.split(",") if m.strip()]
                    mime_q = " or ".join([f"mimeType = '{m}'" for m in mimes])
                    if len(mimes) > 1:
                        q += f" and ({mime_q})"
                    else:
                        q += f" and {mime_q}"
                
                with st.spinner("Loading files from Google Drive..."):
                    files = drive_client.list_files(q=q)
                    st.session_state[f"all_drive_files_{key}"] = files
            except Exception as e:
                st.error(f"Failed to fetch files from Google Drive: {e}")
                st.session_state[f"all_drive_files_{key}"] = []

        all_files = st.session_state.get(f"all_drive_files_{key}", [])
        
        # Local filtering
        if search_query:
            filtered_files = [f for f in all_files if search_query.lower() in f["name"].lower()]
        else:
            filtered_files = all_files

        if not filtered_files:
            st.markdown(
                "<div style='text-align: center; padding: 2rem; color: #8892b0;'>No files found matching the search criteria.</div>", 
                unsafe_allow_html=True
            )
        else:
            selected_file_id = st.session_state.get(f"temp_selected_file_id_{key}")
            
            # 4 Columns Grid layout
            cols_per_row = 4
            for idx in range(0, len(filtered_files), cols_per_row):
                row_files = filtered_files[idx:idx + cols_per_row]
                cols = st.columns(cols_per_row)
                for col_idx, file_item in enumerate(row_files):
                    with cols[col_idx]:
                        file_id = file_item["id"]
                        file_name = file_item["name"]
                        
                        is_selected = (selected_file_id == file_id)
                        card_class = "drive-card drive-card-selected" if is_selected else "drive-card"
                        
                        # SVG Icons based on file type
                        if file_name.lower().endswith(".apk"):
                            # Green Android APK icon
                            icon_svg = """
                            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="#4CAF50" stroke-width="1.5" style="margin-bottom: 12px; filter: drop-shadow(0 0 6px rgba(76, 175, 80, 0.25));">
                                <rect x="3" y="11" width="18" height="10" rx="2"></rect>
                                <circle cx="12" cy="5" r="2"></circle>
                                <path d="M12 7v4" stroke-linecap="round"></path>
                                <line x1="8" y1="16" x2="8" y2="16" stroke-linecap="round" stroke-width="2.5"></line>
                                <line x1="16" y1="16" x2="16" y2="16" stroke-linecap="round" stroke-width="2.5"></line>
                            </svg>
                            """
                        else:
                            # Standard Orange File icon
                            icon_svg = """
                            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="#ff8f00" stroke-width="1.5" style="margin-bottom: 12px; filter: drop-shadow(0 0 6px rgba(255, 143, 0, 0.25));">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="16" y1="13" x2="8" y2="13"></line>
                                <line x1="16" y1="17" x2="8" y2="17"></line>
                            </svg>
                            """
                        
                        # Render Card
                        st.markdown(f"""<div class="{card_class}">{icon_svg}<div class="drive-card-title">{file_name}</div></div>""", unsafe_allow_html=True)
                        st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)
                        
                        btn_label = "✓ Selected" if is_selected else "Select"
                        btn_type = "primary" if is_selected else "secondary"
                        st.button(
                            btn_label, 
                            key=f"sel_btn_{file_id}", 
                            use_container_width=True, 
                            type=btn_type,
                            on_click=select_file_callback,
                            args=(file_id, file_name, key)
                        )

        # Dialog Action Buttons
        st.markdown("<hr style='margin: 1.5rem 0; border: 0; border-top: 1px solid rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
        col_actions_l, col_actions_r = st.columns([1, 1])
        with col_actions_l:
            if st.button("Cancel", use_container_width=True, key=f"cancel_dialog_{key}"):
                st.session_state.pop(f"temp_selected_file_id_{key}", None)
                st.session_state.pop(f"temp_selected_file_name_{key}", None)
                st.rerun()
        with col_actions_r:
            temp_id = st.session_state.get(f"temp_selected_file_id_{key}")
            temp_name = st.session_state.get(f"temp_selected_file_name_{key}")
            if st.button("Select", use_container_width=True, disabled=not temp_id, type="primary", key=f"confirm_dialog_{key}"):
                st.session_state[f"drive_selection_{key}"] = {
                    "file_id": temp_id,
                    "file_name": temp_name,
                    "access_token": token
                }
                st.session_state.pop(f"temp_selected_file_id_{key}", None)
                st.session_state.pop(f"temp_selected_file_name_{key}", None)
                st.rerun()

    with tab_upload:
        st.markdown("<div style='padding: 1.5rem 0;'></div>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Upload directly to Google Drive", type=["apk"])
        if uploaded_file:
            # Future expansion
            st.info("Local upload is ready. Click on the 'Local Upload' radio button on the dashboard sidebar to use it directly.")

def render_drive_picker(
    key: str = "apk",
    label: str = "Connect Google Drive & Pick APK",
    mime_types: str = "application/vnd.android.package-archive",
    height: int = 80,
    token: str = ""
) -> dict | None:
    """
    Renders a Google Drive picker selector button. When clicked, opens a premium dialog
    containing the file picker explorer.
    """
    settings = get_settings()
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID

    # Check if Google Credentials are set
    if (not client_id 
        or client_id == "your-google-oauth-client-id.apps.googleusercontent.com"):
        
        st.error(
            "⚠️ Google Cloud Credentials not fully configured. "
            "Please make sure GOOGLE_OAUTH_CLIENT_ID is correctly set in your .env file."
        )
        return None

    # Get selection
    selection = st.session_state.get(f"drive_selection_{key}")
    
    # Sync token if global token has changed
    if selection and token and selection.get("access_token") != token:
        selection["access_token"] = token
        st.session_state[f"drive_selection_{key}"] = selection

    # Style and render selector control
    st.markdown(f'<div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 0.75rem;"><div style="font-size: 0.9rem; font-weight: 500; color: #8892b0;">Select APK file stored in Google Drive</div></div>', unsafe_allow_html=True)
    
    col_btn, col_info = st.columns([2, 3])
    
    with col_btn:
        button_lbl = "📂 Pick from Drive" if not selection else "🔄 Change File"
        if st.button(button_lbl, key=f"open_dialog_trigger_{key}", use_container_width=True):
            drive_picker_dialog(mime_types, key)
            
    with col_info:
        if selection:
            st.success(f"✓ `{selection['file_name']}`")
        else:
            st.info("No file selected.")

    return selection

def get_auth_html(client_id: str, key: str, label: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://accounts.google.com/gsi/client" async defer></script>
  <style>
     body {{
          margin: 0;
          padding: 0;
          display: flex;
          justify-content: center;
          align-items: flex-start;
          height: 100vh;
          background: transparent;
          font-family: 'Outfit', sans-serif;
          overflow: hidden;
     }}
     .auth-btn {{
          background: linear-gradient(135deg, #ff4b4b 0%, #ff8f00 100%);
          color: white;
          border: none;
          padding: 12px 24px;
          font-size: 16px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
          transition: transform 0.2s, box-shadow 0.2s;
          white-space: nowrap;
     }}
     .auth-btn:hover {{
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(255, 75, 75, 0.6);
     }}
     .auth-btn:active {{
          transform: translateY(1px);
     }}
     .auth-btn:disabled {{
          background: #4a5568;
          box-shadow: none;
          cursor: not-allowed;
     }}
  </style>
</head>
<body>
  <button id="auth-button" class="auth-btn" disabled>Loading Google Auth...</button>
  <script>
    let tokenClient;
    
    window.onload = function() {{
        let gsiInterval = setInterval(() => {{
            if (typeof google !== 'undefined' && google.accounts && google.accounts.oauth2) {{
                clearInterval(gsiInterval);
                enableButton();
            }}
        }}, 100);
    }};

    function enableButton() {{
        const btn = document.getElementById('auth-button');
        btn.disabled = false;
        btn.innerText = "{label}";
        
        tokenClient = google.accounts.oauth2.initTokenClient({{
            client_id: '{client_id}',
            scope: 'https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets',
            callback: (tokenResponse) => {{
                if (tokenResponse && tokenResponse.access_token) {{
                    const currentUrl = new URL(window.top.location.href);
                    currentUrl.searchParams.set('google_auth_token', tokenResponse.access_token);
                    currentUrl.searchParams.set('auth_key', '{key}');
                    window.top.location.href = currentUrl.toString();
                }} else {{
                    console.error("No access token returned", tokenResponse);
                    alert("Authentication failed. Please try again.");
                }}
            }},
        }});
        
        btn.onclick = () => {{
            tokenClient.requestAccessToken({{ prompt: 'consent' }});
        }};
    }}
  </script>
</body>
</html>
"""

def render_google_auth(
    key: str = "google_auth",
    label: str = "Authorize Google Account",
    height: int = 80
) -> str | None:
    """
    Renders a Google OAuth authorization button to fetch an access token.
    """
    settings = get_settings()
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    if not client_id or client_id == "your-google-oauth-client-id.apps.googleusercontent.com":
        st.error("⚠️ Google OAuth Client ID is not configured in .env file.")
        return None

    # Check query params
    query_params = st.query_params
    if "google_auth_token" in query_params:
        target_key = query_params.get("auth_key", "google_auth")
        st.session_state[f"google_auth_token_{target_key}"] = query_params["google_auth_token"]
        # Save token globally so it's shared across the app
        st.session_state["google_auth_token"] = query_params["google_auth_token"]
        st.query_params.clear()
        st.rerun()

    token = st.session_state.get(f"google_auth_token_{key}")
    if not token:
        auth_html = get_auth_html(client_id, key, label)
        components.html(auth_html, height=height)
    return token
