"""Persistent configuration management for Kali-AI Agent."""

import json
import os
import stat
import sys

# Use standard Linux config path: ~/.config/kali-ai/
_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai")
CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "provider": "gemini",  # "openai" or "gemini"
    "openai_api_key": "",
    "openai_base_url": "https://openrouter.ai/api/v1",
    "openai_model": "openai/gpt-4o",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.0-flash",
    "custom_api_key": "",
    "custom_base_url": "",
    "custom_model": "",
    "custom_apis": [],   # unlimited extra endpoints: [{"name","base_url","api_key","model"}]
    "font_size": 13,
    "operator_mode": True,       # never refuse authorized security tasks
    "free_models_only": False,   # OpenRouter: show only free models
    "effort_level": "balanced",  # "fast" | "balanced" | "deep" — reasoning depth vs speed
    "frida_device": "usb",       # Frida target: "usb" (Android/iOS), "local", or "remote:host:port"
}


def _ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    if not os.path.exists(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR, mode=0o700, exist_ok=True)


def _apply_env_overrides(cfg: dict) -> dict:
    """Override config values with environment variables if set."""
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key and not cfg.get("openai_api_key"):
        cfg["openai_api_key"] = env_key

    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and not cfg.get("gemini_api_key"):
        cfg["gemini_api_key"] = env_key

    env_url = os.environ.get("OPENAI_BASE_URL")
    if env_url and not cfg.get("openai_base_url"):
        cfg["openai_base_url"] = env_url

    return cfg


def load_config() -> dict:
    """Load config from file, falling back to defaults and env vars."""
    cfg = dict(DEFAULT_CONFIG)

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            cfg.update(saved)
        except (json.JSONDecodeError, IOError, OSError):
            pass

    # Also check legacy config location (migration support)
    legacy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kali_ai_config.json")
    if not os.path.exists(CONFIG_FILE) and os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r") as f:
                saved = json.load(f)
            cfg.update(saved)
            # Migrate to new location
            save_config(cfg)
        except (json.JSONDecodeError, IOError, OSError):
            pass

    cfg = _apply_env_overrides(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    """Save config to file with restricted permissions."""
    _ensure_config_dir()

    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

    # Restrict file permissions to owner only (Linux/Mac)
    if sys.platform != "win32":
        try:
            os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        except OSError:
            pass
