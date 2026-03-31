"""
Configuration loader - loads and validates all YAML configs.
Single source of truth for all settings.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ── Resolve project root ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


def _load_yaml(path: Path) -> dict:
    """Load a YAML file and return as dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts; override wins on conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Singleton configuration holder."""

    _instance = None
    _settings: dict = {}
    _profile: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """Load settings and profile from YAML files."""
        settings_path = CONFIG_DIR / "settings.yaml"
        profile_path = CONFIG_DIR / "profile.yaml"

        if settings_path.exists():
            self._settings = _load_yaml(settings_path)
        if profile_path.exists():
            self._profile = _load_yaml(profile_path)

        # Override with environment variables
        self._apply_env_overrides()

    def _apply_env_overrides(self):
        """Override config values with environment variables."""
        env_map = {
            "GEMINI_API_KEY": ("ai", "gemini", "api_key"),
            "GROQ_API_KEY": ("ai", "groq", "api_key"),
            "TELEGRAM_BOT_TOKEN": ("notifications", "telegram", "bot_token"),
            "TELEGRAM_CHAT_ID": ("notifications", "telegram", "chat_id"),
            "SMTP_PASSWORD": ("notifications", "email", "sender_password"),
            "GOOGLE_SHEET_ID": ("reporting", "google_sheets", "sheet_id"),
        }
        for env_var, path in env_map.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(self._settings, path, value)

    @staticmethod
    def _set_nested(d: dict, keys: tuple, value: Any):
        """Set a nested dict value by key path."""
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value

    @staticmethod
    def _get_nested(d: dict, keys: tuple, default=None) -> Any:
        """Get a nested dict value by key path."""
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key, default)
            else:
                return default
        return d

    # ── Public API ──────────────────────────────────────────────

    @property
    def settings(self) -> dict:
        return self._settings

    @property
    def profile(self) -> dict:
        return self._profile

    def get(self, *keys, default=None) -> Any:
        """Get a setting by dot-path keys. e.g. config.get('ai', 'gemini', 'api_key')"""
        return self._get_nested(self._settings, keys, default)

    def get_profile(self, *keys, default=None) -> Any:
        """Get a profile value by dot-path keys."""
        return self._get_nested(self._profile, keys, default)

    def get_portal_config(self, portal_name: str) -> dict:
        """Get config for a specific portal."""
        return self._settings.get("portals", {}).get(portal_name, {})

    def is_portal_enabled(self, portal_name: str) -> bool:
        """Check if a portal is enabled."""
        return self.get_portal_config(portal_name).get("enabled", False)

    def reload(self):
        """Force reload configs from disk."""
        self._load()


# ── Convenience singleton ──────────────────────────────────────
config = Config()
