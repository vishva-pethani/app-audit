import streamlit as st
import streamlit.components.v1 as components
from core.config import get_settings

def get_picker_html(client_id: str, api_key: str) -> str:
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
         padding-top: 20px;
         height: 100vh;
         background: transparent;
         font-family: 'Outfit', sans-serif;
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
    let accessToken = null;
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
            btn.innerText = "Connect Google Drive & Pick APK";
            
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

    function createPicker() {{
        if (!accessToken) return;
        
        const apkView = new google.picker.DocsView()
            .setMimeTypes('application/vnd.android.package-archive')
            .setMode(google.picker.DocsViewMode.GRID);
            
        const allView = new google.picker.DocsView()
            .setMode(google.picker.DocsViewMode.GRID);
            
        const picker = new google.picker.PickerBuilder()
            .addView(apkView)
            .addView(allView)
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
            
            window.top.location.href = currentUrl.toString();
        }}
    }}
  </script>
</body>
</html>
"""

def render_drive_picker() -> dict | None:
    """
    Renders the Google Drive Picker UI component in the Streamlit app.
    
    This component handles OAuth 2.0 flow via Google Identity Services (GIS)
    entirely client-side in the browser, requesting scopes for Google Drive and Sheets,
    and displays the interactive Google Drive Picker to let users select the target APK.
    
    Due to Streamlit iframe isolation, client-side JavaScript values cannot be returned
    directly to the Python backend. Instead, we use a query-parameter redirect mechanism:
    1. The client-side picker redirects the parent window (window.top) to append the
       oauth token, file ID, and file name as URL query parameters.
    2. The Python code detects these parameters, stores them in `st.session_state`,
       clears the query parameters from the URL, and triggers `st.rerun()`.
    3. The app is re-run with a clean URL and the selection safely stored in session state.
    
    Returns:
        dict | None: A dictionary containing 'file_id', 'file_name', and 'access_token'
                     if a file has been selected; otherwise None.
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
        st.session_state["drive_selection"] = {
            "file_id": query_params["drive_file_id"],
            "file_name": query_params["drive_file_name"],
            "access_token": query_params["drive_access_token"]
        }
        # Clear query params and rerun to clean URL
        st.query_params.clear()
        st.rerun()

    # Render picker UI in an iframe
    picker_html = get_picker_html(client_id, api_key)
    components.html(picker_html, height=600)

    return st.session_state.get("drive_selection")
