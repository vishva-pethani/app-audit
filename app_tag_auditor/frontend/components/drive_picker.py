"""
drive_picker.py
---------------
Google Drive file input provider for Streamlit.
Parses a Google Drive URL or File ID directly and resolves metadata.
"""
import streamlit as st
import streamlit.components.v1 as components
import requests
import re
from core.config import get_settings

def extract_drive_file_id(url: str) -> str | None:
    if not url:
        return None
    url = url.strip()
    # Pattern 1: /file/d/<FILE_ID>
    match1 = re.search(r"/file/d/([a-zA-Z0-9_-]{25,100})", url)
    if match1:
        return match1.group(1)
    # Pattern 2: id=<FILE_ID>
    match2 = re.search(r"id=([a-zA-Z0-9_-]{25,100})", url)
    if match2:
        return match2.group(1)
    # If it is already a direct file ID
    if re.match(r"^[a-zA-Z0-9_-]{25,100}$", url):
        return url
    return None

def get_drive_file_name(file_id: str, token: str) -> str | None:
    if not token:
        return None
    try:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("name")
    except Exception:
        pass
    return None

def render_drive_picker(
    key: str = "apk",
    label: str = "Open Google Drive",
    mime_types: str = "application/vnd.android.package-archive",
    height: int = 80,
    token: str = "",
) -> dict | None:
    """
    Renders a URL/ID input box. Auto-parses the file ID and resolves the file name.
    """
    st.markdown("""
<style>
.drive-url-box {
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
        <div class="drive-url-box">
            <div style="font-size: 0.9rem; font-weight: 500; color: #8892b0; margin-bottom: 0.75rem;">Google Drive File Link / ID</div>
        """, unsafe_allow_html=True)
        
        # User input for the Drive URL
        input_key = f"drive_url_input_{key}"
        url_input = st.text_input(
            "Paste Google Drive file link or ID",
            placeholder="https://drive.google.com/file/d/.../view",
            key=input_key,
            label_visibility="collapsed"
        )
        
        file_id = extract_drive_file_id(url_input)
        
        if not url_input:
            st.markdown("<div style='color: #8892b0; font-size: 0.85rem;'>Please paste a Google Drive file link or a file ID.</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            return None
            
        if not file_id:
            st.error("⚠️ Invalid format. Could not parse Google Drive File ID from input.")
            st.markdown("</div>", unsafe_allow_html=True)
            return None
            
        # Retrieve original name if authenticated
        resolved_name = None
        if token:
            resolved_name = get_drive_file_name(file_id, token)
            
        file_name = resolved_name or "drive_file.apk"
        
        if resolved_name:
            st.success(f"✓ Resolved File: `{resolved_name}`")
        else:
            st.info(f"📁 Parsed File ID: `{file_id}` (Sign in below to authenticate download)")
            
        st.markdown("</div>", unsafe_allow_html=True)
        
        return {
            "file_id": file_id,
            "file_name": file_name,
            "access_token": token
        }

# ---------------------------------------------------------------------------
# Google auth button (used for authentication / Sheets URL flow)
# ---------------------------------------------------------------------------

def _auth_button_html(client_id: str, key: str, label: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://accounts.google.com/gsi/client" async defer></script>
<style>
  body{{margin:0;padding:0;display:flex;justify-content:center;align-items:flex-start;height:100vh;background:transparent;overflow:hidden;font-family:-apple-system,sans-serif;}}
  .btn{{background:linear-gradient(135deg,#ff4b4b,#ff8f00);color:#fff;border:none;border-radius:8px;padding:11px 22px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 3px 12px rgba(255,75,75,.4);transition:opacity .15s,transform .15s;}}
  .btn:hover{{opacity:.9;transform:translateY(-1px);}}
  .btn:disabled{{background:#2d3748;box-shadow:none;cursor:not-allowed;color:#718096;}}
</style></head>
<body>
<button id="b" class="btn" disabled>Loading…</button>
<script>
  const CLIENT_ID="{client_id}";
  const KEY="{key}";
  const LABEL={repr(label)};
  let tc;
  (function poll(){{
    if(typeof google!=="undefined"&&google.accounts&&google.accounts.oauth2){{
      tc=google.accounts.oauth2.initTokenClient({{
        client_id:CLIENT_ID,
        scope:"https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets",
        callback:(r)=>{{
          if(r&&r.access_token){{
            const u=new URL("/", window.location.origin);
            u.searchParams.set("google_auth_token",r.access_token);
            u.searchParams.set("auth_key",KEY);
            window.parent.location.replace(u.toString());
          }} else alert("Auth failed – please try again.");
        }}
      }});
      const b=document.getElementById("b");
      b.textContent=LABEL;b.disabled=false;
      b.onclick=()=>tc.requestAccessToken({{prompt:"consent"}});
    }} else setTimeout(poll,120);
  }})();
</script>
</body></html>
"""

def render_google_auth(
    key: str = "google_auth",
    label: str = "Authorize Google Account",
    height: int = 80,
) -> str | None:
    """Renders an OAuth sign-in button and returns the token once obtained."""
    settings = get_settings()
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    if not client_id or client_id == "your-google-oauth-client-id.apps.googleusercontent.com":
        st.error("⚠️ GOOGLE_OAUTH_CLIENT_ID is not configured.")
        return None

    # Capture callback from redirect
    qp = st.query_params
    if "google_auth_token" in qp:
        target_key = qp.get("auth_key", "google_auth")
        st.session_state[f"google_auth_token_{target_key}"] = qp["google_auth_token"]
        st.session_state["google_auth_token"]                = qp["google_auth_token"]
        st.query_params.clear()
        st.rerun()

    token = st.session_state.get(f"google_auth_token_{key}")
    if not token:
        components.html(_auth_button_html(client_id, key, label), height=height)
    return token
