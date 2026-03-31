"""Tests for configuration loading and validation."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestConfig:
    """Test configuration loading and validation."""

    def test_project_root_resolves(self):
        """PROJECT_ROOT should resolve to the actual project directory."""
        from src.core.config import PROJECT_ROOT
        assert PROJECT_ROOT.exists()
        assert (PROJECT_ROOT / "config").is_dir()

    def test_config_is_singleton(self):
        """Config should be a singleton — same instance every time."""
        from src.core.config import Config
        c1 = Config()
        c2 = Config()
        assert c1 is c2

    def test_config_loads_settings_yaml(self):
        """Settings should be loaded from config/settings.yaml."""
        from src.core.config import config
        # Should have basic structure
        assert isinstance(config.settings, dict)
        assert "app" in config.settings or config.settings == {}

    def test_config_get_nested(self):
        """Config.get() should support nested key paths."""
        from src.core.config import Config
        result = Config._get_nested(
            {"a": {"b": {"c": 42}}},
            ("a", "b", "c"),
        )
        assert result == 42

    def test_config_get_nested_default(self):
        """Config.get() should return default for missing keys."""
        from src.core.config import Config
        result = Config._get_nested(
            {"a": {"b": 1}},
            ("a", "x", "y"),
            default="fallback",
        )
        assert result == "fallback"

    def test_config_set_nested(self):
        """Config._set_nested() should set deeply nested values."""
        d = {}
        from src.core.config import Config
        Config._set_nested(d, ("a", "b", "c"), "value")
        assert d == {"a": {"b": {"c": "value"}}}

    def test_env_override(self):
        """Environment variables should override YAML config."""
        from src.core.config import Config
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-test-key"}):
            c = Config.__new__(Config)
            c._settings = {"ai": {"gemini": {"api_key": "yaml-key"}}}
            c._profile = {}
            c._apply_env_overrides()
            assert c._settings["ai"]["gemini"]["api_key"] == "env-test-key"

    def test_get_portal_config(self):
        """get_portal_config should return portal-specific dict."""
        from src.core.config import config
        # Even if portals don't exist, should return empty dict
        result = config.get_portal_config("nonexistent_portal")
        assert isinstance(result, dict)


class TestConfigValidation:
    """Test configuration validation warnings."""

    def test_validate_warns_missing_api_key(self, capsys):
        """Should warn when Gemini API key is missing."""
        from src.core.config import Config
        c = Config.__new__(Config)
        c._settings = {"ai": {"provider": "gemini", "gemini": {"api_key": ""}}, "portals": {"linkedin": {"enabled": True}}}
        c._profile = {"personal": {"email": "test@example.com"}, "job_search": {"keywords": ["SDET"]}}
        c._validate()
        captured = capsys.readouterr()
        assert "Gemini API key not set" in captured.err

    def test_validate_warns_no_portals_enabled(self, capsys):
        """Should warn when no portals are enabled."""
        from src.core.config import Config
        c = Config.__new__(Config)
        c._settings = {"ai": {"provider": "gemini", "gemini": {"api_key": "key123"}}, "portals": {"linkedin": {"enabled": False}}}
        c._profile = {"personal": {"email": "test@example.com"}, "job_search": {"keywords": ["SDET"]}}
        c._validate()
        captured = capsys.readouterr()
        assert "No portals are enabled" in captured.err

    def test_validate_warns_default_email(self, capsys):
        """Should warn when profile email is the example placeholder."""
        from src.core.config import Config
        c = Config.__new__(Config)
        c._settings = {"ai": {"provider": "gemini", "gemini": {"api_key": "key"}}, "portals": {"x": {"enabled": True}}}
        c._profile = {"personal": {"email": "your.email@example.com"}, "job_search": {"keywords": ["SDET"]}}
        c._validate()
        captured = capsys.readouterr()
        assert "Profile email not configured" in captured.err
