"""
Persistent Chat Sessions Manager for Kali-AI Agent.
Saves and loads all past chat conversation sessions to/from ~/.config/kali-ai/sessions.json
ensuring complete persistence across application restarts.
"""

import json
import os

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai")
SESSIONS_FILE = os.path.join(_CONFIG_DIR, "sessions.json")


def _ensure_dir():
    if not os.path.exists(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR, mode=0o700, exist_ok=True)


def load_all_sessions() -> list[dict]:
    """Load all saved past chat sessions from disk."""
    _ensure_dir()
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_all_sessions(sessions: list[dict]) -> None:
    """Save all past chat sessions to disk."""
    _ensure_dir()
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def delete_session_by_id(session_id: int) -> list[dict]:
    """Delete a session by ID from disk and return remaining sessions."""
    sessions = load_all_sessions()
    filtered = [s for s in sessions if s.get("id") != session_id]
    save_all_sessions(filtered)
    return filtered
