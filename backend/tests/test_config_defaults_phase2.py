"""Unit tests for Phase 2 config default value changes.

Tests that hyde_enabled and context_distillation_enabled default to True
and can be overridden via environment variables.

Note: The "other defaults unchanged" tests verify the code-defined defaults
in config.py, but these may be overridden by user environment variables (.env file).
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings


class TestHyDeEnabledDefaults:
    """Test hyde_enabled default value and env override."""

    def test_hyde_enabled_defaults_true(self, monkeypatch):
        """Test that hyde_enabled defaults to True in config.py."""
        # Clear any existing HYDE_ENABLED from environment
        monkeypatch.delenv("HYDE_ENABLED", raising=False)
        settings = Settings()
        assert settings.hyde_enabled is True

    def test_hyde_enabled_env_override(self, monkeypatch):
        """Test that HYDE_ENABLED=false env var overrides default."""
        monkeypatch.setenv("HYDE_ENABLED", "false")
        settings = Settings()
        assert settings.hyde_enabled is False

    def test_hyde_enabled_env_override_true(self, monkeypatch):
        """Test that HYDE_ENABLED=true explicitly sets True."""
        monkeypatch.setenv("HYDE_ENABLED", "true")
        settings = Settings()
        assert settings.hyde_enabled is True


class TestContextDistillationEnabledDefaults:
    """Test context_distillation_enabled default value and env override."""

    def test_context_distillation_enabled_defaults_true(self, monkeypatch):
        """Test that context_distillation_enabled defaults to True in config.py."""
        # Clear any existing CONTEXT_DISTILLATION_ENABLED from environment
        monkeypatch.delenv("CONTEXT_DISTILLATION_ENABLED", raising=False)
        settings = Settings()
        assert settings.context_distillation_enabled is True

    def test_context_distillation_env_override(self, monkeypatch):
        """Test that CONTEXT_DISTILLATION_ENABLED=false env var overrides default."""
        monkeypatch.setenv("CONTEXT_DISTILLATION_ENABLED", "false")
        settings = Settings()
        assert settings.context_distillation_enabled is False

    def test_context_distillation_env_override_true(self, monkeypatch):
        """Test that CONTEXT_DISTILLATION_ENABLED=true explicitly sets True."""
        monkeypatch.setenv("CONTEXT_DISTILLATION_ENABLED", "true")
        settings = Settings()
        assert settings.context_distillation_enabled is True


class TestConfigPydanticSettingsBehavior:
    """Test that Pydantic Settings correctly parses boolean env vars."""

    def test_bool_env_var_parsing_lowercase_false(self, monkeypatch):
        """Test that 'false' (lowercase) is parsed as boolean False."""
        monkeypatch.setenv("HYDE_ENABLED", "false")
        settings = Settings()
        assert settings.hyde_enabled is False
        assert isinstance(settings.hyde_enabled, bool)

    def test_bool_env_var_parsing_uppercase_false(self, monkeypatch):
        """Test that 'FALSE' (uppercase) is parsed as boolean False."""
        monkeypatch.setenv("HYDE_ENABLED", "FALSE")
        settings = Settings()
        assert settings.hyde_enabled is False

    def test_bool_env_var_parsing_zero(self, monkeypatch):
        """Test that '0' is parsed as boolean False."""
        monkeypatch.setenv("HYDE_ENABLED", "0")
        settings = Settings()
        assert settings.hyde_enabled is False

    def test_bool_env_var_parsing_one(self, monkeypatch):
        """Test that '1' is parsed as boolean True."""
        monkeypatch.setenv("HYDE_ENABLED", "1")
        settings = Settings()
        assert settings.hyde_enabled is True
