"""
Tests for Settings model security validators.

Tests cover:
- reject_insecure_defaults: Validates admin_secret_token when users_enabled=True
- validate_hyde_config: Warns when HyDE is enabled without query transformation
"""

import warnings
import pytest
from app.config import Settings


class TestRejectInsecureDefaults:
    """Tests for the reject_insecure_defaults model validator."""

    def test_users_enabled_with_empty_admin_token_raises_error(self):
        """users_enabled=True, admin_secret_token="" should raise ValueError."""
        with pytest.raises(ValueError, match="ADMIN_SECRET_TOKEN must be set"):
            Settings(users_enabled=True, admin_secret_token="")

    def test_users_enabled_with_nonempty_admin_token_succeeds(self):
        """users_enabled=True, admin_secret_token="something" should not raise."""
        # Should not raise
        settings = Settings(users_enabled=True, admin_secret_token="secure-token-123")
        assert settings.users_enabled is True
        assert settings.admin_secret_token == "secure-token-123"

    def test_users_disabled_with_empty_admin_token_raises(self):
        """users_enabled=False, admin_secret_token="" should raise — sole auth mechanism is unset."""
        with pytest.raises(ValueError, match="ADMIN_SECRET_TOKEN must be set when USERS_ENABLED=False"):
            Settings(users_enabled=False, admin_secret_token="")

    def test_users_disabled_with_nonempty_admin_token_succeeds(self):
        """users_enabled=False, admin_secret_token="something" should not raise."""
        # Should not raise
        settings = Settings(users_enabled=False, admin_secret_token="some-token")
        assert settings.users_enabled is False
        assert settings.admin_secret_token == "some-token"


class TestValidateHydeConfig:
    """Tests for the validate_hyde_config model validator."""

    def test_hyde_enabled_without_query_transformation_warns(self):
        """hyde_enabled=True, query_transformation_enabled=False should emit UserWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(hyde_enabled=True, query_transformation_enabled=False)
            # Verify a UserWarning was raised
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)
            assert "HyDE is enabled but query_transformation_enabled is False" in str(
                w[0].message
            )

    def test_hyde_enabled_with_query_transformation_no_warning(self):
        """hyde_enabled=True, query_transformation_enabled=True should not emit warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(hyde_enabled=True, query_transformation_enabled=True)
            # Verify no warnings were raised
            assert len(w) == 0

    def test_hyde_disabled_without_query_transformation_no_warning(self):
        """hyde_enabled=False, query_transformation_enabled=False should not emit warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(hyde_enabled=False, query_transformation_enabled=False)
            # Verify no warnings were raised
            assert len(w) == 0

    def test_hyde_disabled_with_query_transformation_no_warning(self):
        """hyde_enabled=False, query_transformation_enabled=True should not emit warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(hyde_enabled=False, query_transformation_enabled=True)
            # Verify no warnings were raised
            assert len(w) == 0
