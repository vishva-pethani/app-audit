import streamlit as st
import streamlit.components.v1 as components
from core.config import get_settings
import os

def get_picker_html(client_id: str, api_key: str, key: str, mime_types: str) -> str:
    """
    Generates the HTML/JS markup for the client-side Google Drive Picker with Upload support.
    """
    # Vector illustration of Google Drive / Cloud
    svg_illustration = """
    <svg viewBox="0 0 24 24" width="64" height="64" fill="none" stroke="#ff8f00" stroke-width="1.5" style="filter: drop-shadow(0 0 12px rgba(255, 143, 0, 0.45));">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke-linejoin="round" stroke-linecap="round"></path>
    </svg>
    """
    
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://accounts.google.com/gsi/client" async defer></script>
  <script src="https://apis.google.com/js/api.js" async defer></script>
  <style>
     body {{
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          height: 100vh;
          background-color: #0e1117;
          color: #fafafa;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
     }}
     .card {{
          background: #1e293b;
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 2.5rem;
          text-align: center;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
          max-width: 400px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1.5rem;
     }}
     .logo {{
          margin-bottom: 0.5rem;
     }}
     .title {{
          font-size: 1.25rem;
          font-weight: 600;
          margin: 0;
          color: #ffffff;
     }}
     .subtitle {{
          font-size: 0.9rem;
          color: #8892b0;
          margin: 0;
          line-height: 1.5;
     }}
     .auth-btn {{
          background: linear-gradient(135deg, #ff4b4b 0%, #ff8f00 100%);
          color: white;
          border: none;
          padding: 14px 28px;
          font-size: 15px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
          transition: transform 0.2s, box-shadow 0.2s;
          width: 100%;
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
          color: #a0aec0;
     }}
  </style>
</head>
<body>
  <div class="card">
      <div class="logo">{svg_illustration}</div>
      <h2 class="title">Google Drive Picker</h2>
      <p class="subtitle">Authorize and choose your file from Google Drive, or upload directly using Google's native secure panel.</p>
      <button id="picker-button" class="auth-btn" disabled>Loading Google APIs...</button>
  </div>
  <script>
    let tokenClient;
    let accessToken = null;
    let pickerApiLoaded = false;
    let gsiLoaded = false;

    function onApiLoad() {{
        gapi.load('picker', () => {{
            pickerApiLoaded = true;
            enableButtonIfReady();
        }});
    }}

    window.onload = function() {{
        if (typeof gapi !== 'undefined') {{
            onApiLoad();
        }} else {{
            let interval = setInterval(() => {{
                if (typeof gapi !== 'undefined') {{
                    clearInterval(interval);
                    onApiLoad();
                }}
            }}, 100);
        }}
        
        let gsiInterval = setInterval(() => {{
            if (typeof google !== 'undefined' && google.accounts && google.accounts.oauth2) {{
                clearInterval(gsiInterval);
                gsiLoaded = true;
                enableButtonIfReady();
            }}
        }}, 100);
    }};

    function enableButtonIfReady() {{
        const btn = document.getElementById('picker-button');
        if (pickerApiLoaded && gsiLoaded) {{
            btn.disabled = false;
            btn.innerText = "Authorize & Open Picker";
            
            tokenClient = google.accounts.oauth2.initTokenClient({{
                client_id: '{client_id}',
                scope: 'https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets',
                callback: (tokenResponse) => {{
                    if (tokenResponse && tokenResponse.access_token) {{
                        accessToken = tokenResponse.access_token;
                        createPicker();
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
    }}

    function createPicker() {{
        if (!accessToken) return;
        
        const docsView = new google.picker.DocsView()
            .setMimeTypes('{mime_types}')
            .setMode(google.picker.DocsViewMode.GRID);
            
        const uploadView = new google.picker.DocsUploadView();
        
        const picker = new google.picker.PickerBuilder()
            .addView(docsView)
            .addView(uploadView)
            .setOAuthToken(accessToken)
            .setDeveloperKey('{api_key}')
            .setCallback(pickerCallback)
            .setSize(700, 500)
            .build();
            
        picker.setVisible(true);
    }}

    function pickerCallback(data) {{
        if (data.action == google.picker.Action.PICKED) {{
            const doc = data.docs[0];
            const fileId = doc.id;
            const fileName = doc.name;
            
            const currentUrl = new URL(window.top.location.href);
            currentUrl.searchParams.set('drive_file_id', fileId);
            currentUrl.searchParams.set('drive_file_name', fileName);
            currentUrl.searchParams.set('drive_access_token', accessToken);
            currentUrl.searchParams.set('picker_key', '{key}');
            
            window.top.location.href = currentUrl.toString();
        }}
    }}
  </script>
</body>
</html>
"""

@st.dialog("Google Drive Native Picker", width="large")
def drive_picker_dialog(mime_types: str, key: str):
    """
    Renders the dialog box enclosing the Google Picker iframe.
    """
    settings = get_settings()
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    api_key = settings.GOOGLE_API_KEY
    
    if not client_id or not api_key or client_id == "your-google-oauth-client-id.apps.googleusercontent.com" or api_key == "your-google-api-key":
        st.error("⚠️ Google OAuth Client ID or API Key is not fully configured in your .env file.")
        return
        
    picker_html = get_picker_html(client_id, api_key, key, mime_types)
    components.html(picker_html, height=580)

def render_drive_picker(
    key: str = "apk",
    label: str = "Connect Google Drive & Pick APK",
    mime_types: str = "application/vnd.android.package-archive",
    height: int = 80,
    token: str = ""
) -> dict | None:
    """
    Renders the selector controller on the dashboard page.
    """
    # Parse query parameters first
    query_params = st.query_params
    if "drive_file_id" in query_params and "drive_file_name" in query_params and "drive_access_token" in query_params:
        target_key = query_params.get("picker_key", "apk")
        st.session_state[f"drive_selection_{target_key}"] = {
            "file_id": query_params["drive_file_id"],
            "file_name": query_params["drive_file_name"],
            "access_token": query_params["drive_access_token"]
        }
        st.session_state["google_auth_token"] = query_params["drive_access_token"]
        st.query_params.clear()
        st.rerun()

    # Get selection
    selection = st.session_state.get(f"drive_selection_{key}")
    
    # Sync token if global token has changed
    if selection and token and selection.get("access_token") != token:
        selection["access_token"] = token
        st.session_state[f"drive_selection_{key}"] = selection

    # Style
    st.markdown("""
<style>
.drive-selector-box {
    background-color: var(--secondary-background-color) !important;
    border: 1px solid rgba(128, 128, 128, 0.15) !important;
    border-radius: 12px !important;
    padding: 1.25rem !important;
    margin-bottom: 1rem !important;
}
</style>
""", unsafe_allow_html=True)

    with st.container():
        st.markdown(f"""
        <div class="drive-selector-box">
            <div style="font-size: 0.9rem; font-weight: 500; color: #8892b0; margin-bottom: 0.75rem;">Select file from Google Drive / Cloud</div>
        """, unsafe_allow_html=True)
        
        col_btn, col_info = st.columns([2, 3])
        
        with col_btn:
            button_lbl = "📂 Open Google Picker" if not selection else "🔄 Change File"
            if st.button(button_lbl, key=f"open_dialog_trigger_{key}", use_container_width=True, type="primary" if not selection else "secondary"):
                if selection:
                    # Reset selection
                    st.session_state.pop(f"drive_selection_{key}", None)
                    st.rerun()
                else:
                    drive_picker_dialog(mime_types, key)
                    
        with col_info:
            if selection:
                st.markdown(f"""
                <div style="background: rgba(46, 204, 113, 0.05); border: 1px solid #2ecc71; border-radius: 8px; padding: 6px 12px; display: inline-block;">
                    <span style="color: #2ecc71; font-weight: 600; font-size: 0.9rem;">✓ {selection['file_name']}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="padding: 6px 0; color: #8892b0; font-size: 0.9rem;">No file selected.</div>
                """, unsafe_allow_html=True)
                
        st.markdown("</div>", unsafe_allow_html=True)

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
          font-family: -apple-system, BlinkMacSystemFont, sans-serif;
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
            scope: 'https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets',
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
