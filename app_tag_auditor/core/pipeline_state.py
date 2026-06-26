"""
pipeline_state.py — Server-wide singleton pipeline state.

Uses a JSON file on disk as the source of truth so ALL Streamlit sessions
(tabs, users, refreshes) see the same running/idle state.

State file schema:
{
    "running": true,
    "started_at": "2026-06-26T07:00:00",
    "apk_name": "myapp.apk",
    "log_lines": ["line1", "line2", ...],   # rolling last 500 lines
    "error": null | "error message",
    "completed": false
}
"""

import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path

_STATE_DIR = Path(os.environ.get("TEMP_STORAGE_DIR", "./tmp"))
_STATE_FILE = _STATE_DIR / ".pipeline_state.json"
_LOG_FILE = _STATE_DIR / ".pipeline_log.jsonl"
_MAX_LOG_LINES = 500

_write_lock = threading.Lock()


def _ensure_dir():
    _STATE_DIR.mkdir(parents=True, exist_ok=True)


# ── Readers ────────────────────────────────────────────────────────────────────

def get_state() -> dict:
    """Return the current pipeline state dict. Safe to call from any thread."""
    _ensure_dir()
    try:
        raw = _STATE_FILE.read_text(encoding="utf-8")
        return json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        return _empty_state()


def get_log_lines() -> list[str]:
    """Return all log lines captured so far (last _MAX_LOG_LINES)."""
    _ensure_dir()
    try:
        lines = _LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l)["msg"] for l in lines if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def is_running() -> bool:
    return get_state().get("running", False)


# ── Writers ────────────────────────────────────────────────────────────────────

def _empty_state() -> dict:
    return {
        "running": False,
        "started_at": None,
        "apk_name": "",
        "error": None,
        "completed": False,
    }


def _write_state(state: dict):
    _ensure_dir()
    with _write_lock:
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def start_pipeline(apk_name: str):
    """Mark pipeline as started. Call before spawning the thread."""
    _ensure_dir()
    # Clear old log
    with _write_lock:
        _LOG_FILE.write_text("", encoding="utf-8")
    _write_state({
        "running": True,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "apk_name": apk_name,
        "error": None,
        "completed": False,
    })


def finish_pipeline(error: str | None = None):
    """Mark pipeline as finished (success or failure)."""
    state = get_state()
    state["running"] = False
    state["completed"] = (error is None)
    state["error"] = error
    _write_state(state)


def append_log(msg: str):
    """Append a single log line. Called from the logging handler thread."""
    _ensure_dir()
    entry = json.dumps({"ts": time.time(), "msg": msg}, ensure_ascii=False)
    with _write_lock:
        # Keep file bounded: read, trim, rewrite if too large
        try:
            existing = _LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
        except FileNotFoundError:
            existing = []
        existing.append(entry)
        if len(existing) > _MAX_LOG_LINES:
            existing = existing[-_MAX_LOG_LINES:]
        _LOG_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")


def reset():
    """Clear pipeline state entirely (e.g. on server boot)."""
    _write_state(_empty_state())
    _ensure_dir()
    try:
        _LOG_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass
