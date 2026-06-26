"""
Server-side session store for persistent Google OAuth sessions.

Flow:
  1. On first login, a random session_token is generated.
  2. Auth data (access_token, refresh_token, expiry, user_profile) is saved to a
     JSON file at SESSIONS_DIR/<session_token>.json.
  3. The session_token itself is stored in the browser's localStorage.
  4. On every subsequent page load, JS reads the session_token from localStorage
     and appends it as ?session_token=<token> to the URL via window.location.replace.
  5. Python reads st.query_params["session_token"], loads the session file, and
     restores the session — no JS-to-textarea hacks needed.
  6. Sessions expire after SESSION_TTL_SECONDS (default: 7 days).
"""

import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

# Store sessions in a persistent volume path (mapped in docker-compose)
_DEFAULT_SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".sessions"
)
SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", _DEFAULT_SESSIONS_DIR))
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# 7 days in seconds
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60


def _session_path(token: str) -> Path:
    # Sanitize token — only alphanumeric + hyphen allowed
    safe = "".join(c for c in token if c.isalnum() or c == "-")
    return SESSIONS_DIR / f"{safe}.json"


def create_session(access_token: str, refresh_token: Optional[str],
                   expiry: str, profile: dict) -> str:
    """Persist a new session and return the session token."""
    token = secrets.token_urlsafe(32)
    data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expiry": expiry,
        "profile": profile,
        "created_at": time.time(),
        "last_seen": time.time(),
    }
    _session_path(token).write_text(json.dumps(data), encoding="utf-8")
    return token


def load_session(token: str) -> Optional[dict]:
    """Load session data by token. Returns None if expired or missing."""
    path = _session_path(token)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    age = time.time() - data.get("created_at", 0)
    if age > SESSION_TTL_SECONDS:
        path.unlink(missing_ok=True)
        return None

    # Update last_seen
    data["last_seen"] = time.time()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def update_session(token: str, access_token: str, expiry: str) -> bool:
    """Update the access token + expiry for an existing session."""
    path = _session_path(token)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["access_token"] = access_token
        data["expiry"] = expiry
        data["last_seen"] = time.time()
        path.write_text(json.dumps(data), encoding="utf-8")
        return True
    except (json.JSONDecodeError, OSError):
        return False


def delete_session(token: str) -> None:
    """Delete a session (sign-out)."""
    _session_path(token).unlink(missing_ok=True)


def purge_expired() -> int:
    """Remove all sessions older than SESSION_TTL_SECONDS. Returns count removed."""
    removed = 0
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if time.time() - data.get("created_at", 0) > SESSION_TTL_SECONDS:
                f.unlink(missing_ok=True)
                removed += 1
        except (json.JSONDecodeError, OSError):
            f.unlink(missing_ok=True)
            removed += 1
    return removed
