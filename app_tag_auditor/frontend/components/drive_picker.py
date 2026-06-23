import streamlit as st
import streamlit.components.v1 as components
from core.config import get_settings

def get_picker_html(client_id: str, api_key: str, key: str, mime_types: str, label: str, token: str = "") -> str:
    """
    Generates the HTML/JS markup for the client-side Google Drive Picker.
    
    Loads Google Identity Services (GSI) and Google APIs (gapi) scripts,
    authenticates the user client-side, and displays the Drive Picker.
    Once a file is picked, it redirects the top window to pass the
    selected file's metadata and OAuth token back to Python via URL query parameters.
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
          justify-content: center;
          align-items: flex-start;
          height: 100vh;
          background: transparent;
          font-family: 'Outfit', sans-serif;
          overflow: hidden;
     }}
     .picker-btn {{
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
     .picker-btn:hover {{
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(255, 75, 75, 0.6);
     }}
     .picker-btn:active {{
          transform: translateY(1px);
     }}
     .picker-btn:disabled {{
          background: #4a5568;
          box-shadow: none;
          cursor: not-allowed;
     }}
  </style>
</head>
<body>
  <button id="picker-button" class="picker-btn" disabled>Loading Google APIs...</button>
  <script>
    let tokenClient;
    let accessToken = "{token}" || null;
    let pickerApiLoaded = false;

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
                enableButtonIfReady();
            }}
        }}, 100);
    }};

    function enableButtonIfReady() {{
        const btn = document.getElementById('picker-button');
        if (pickerApiLoaded && typeof google !== 'undefined' && google.accounts && google.accounts.oauth2) {{
            btn.disabled = false;
            btn.innerText = "{label}";
            
            if (accessToken) {{
                btn.onclick = () => {{
                    createPicker();
                }};
            }} else {{
                tokenClient = google.accounts.oauth2.initTokenClient({{
                    client_id: '{client_id}',
                    scope: 'https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets',
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
    }}

    function createPicker() {{
        if (!accessToken) return;
        
        const docsView = new google.picker.DocsView()
            .setMimeTypes('{mime_types}')
            .setMode(google.picker.DocsViewMode.GRID);
            
        const picker = new google.picker.PickerBuilder()
            .addView(docsView)
            .setOAuthToken(accessToken)
            .setDeveloperKey('{api_key}')
            .setCallback(pickerCallback)
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

def render_drive_picker(
    key: str = "apk",
    label: str = "Connect Google Drive & Pick APK",
    mime_types: str = "application/vnd.android.package-archive",
    height: int = 80,
    token: str = ""
) -> dict | None:
    """
    Renders the Google Drive Picker UI component in the Streamlit app.
    
    This component handles OAuth 2.0 flow via Google Identity Services (GIS)
    entirely client-side in the browser, requesting scopes for Google Drive and Sheets,
    and displays the interactive Google Drive Picker to let users select files.
    
    Returns:
        dict | None: A dictionary containing 'file_id', 'file_name', and 'access_token'
                     if a file has been selected for this key; otherwise None.
    """
    settings = get_settings()
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    api_key = settings.GOOGLE_API_KEY

    # Check if Google Credentials are set
    if (not client_id 
        or not api_key 
        or client_id == "your-google-oauth-client-id.apps.googleusercontent.com" 
        or api_key == "your-google-api-key"):
        
        st.error(
            "⚠️ Google Cloud Credentials not fully configured. "
            "Please make sure GOOGLE_OAUTH_CLIENT_ID and GOOGLE_API_KEY are correctly set in your .env file."
        )
        return None

    # Check URL query parameters for returning values
    query_params = st.query_params
    if "drive_file_id" in query_params and "drive_file_name" in query_params and "drive_access_token" in query_params:
        target_key = query_params.get("picker_key", "apk")
        st.session_state[f"drive_selection_{target_key}"] = {
            "file_id": query_params["drive_file_id"],
            "file_name": query_params["drive_file_name"],
            "access_token": query_params["drive_access_token"]
        }
        # Save token globally so it's shared across the app
        st.session_state["google_auth_token"] = query_params["drive_access_token"]
        # Clear query params and rerun to clean URL
        st.query_params.clear()
        st.rerun()

    # Get selection
    selection = st.session_state.get(f"drive_selection_{key}")
    
    # If we have a global token, ensure it is synchronized to the selection if present
    if selection and token and selection.get("access_token") != token:
        selection["access_token"] = token
        st.session_state[f"drive_selection_{key}"] = selection

    # Determine which token to pass to the HTML iframe
    passed_token = token or (selection.get("access_token") if selection else "")

    # Render picker UI in an iframe
    picker_html = get_picker_html(client_id, api_key, key, mime_types, label, passed_token)
    components.html(picker_html, height=height)

    return st.session_state.get(f"drive_selection_{key}")

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
