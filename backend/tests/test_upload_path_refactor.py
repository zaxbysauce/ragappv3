"""Tests for UploadPathProvider refactor - verifying no DB calls and no _get_vault_name."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from app.services.upload_path import UploadPathProvider


class TestUploadPathProviderRefactor:
    """Tests verifying the UploadPathProvider refactor."""

    def test_get_upload_dir_returns_mocked_path(self):
        """Test get_upload_dir returns exactly what settings.vault_uploads_dir returns."""
        mock_vault_path = Path("/mocked/vaults/42/uploads")

        with patch("app.services.upload_path.settings") as mock_settings:
            mock_settings.vault_uploads_dir.return_value = mock_vault_path

            provider = UploadPathProvider()
            result = provider.get_upload_dir(42)

            # EXACT VALUE ASSERTION
            assert result == mock_vault_path
            # VERIFY CALL
            mock_settings.vault_uploads_dir.assert_called_once_with(42)

    def test_get_upload_dir_no_database_call(self):
        """Verify get_upload_dir does not trigger any database calls."""
        with patch("app.services.upload_path.settings") as mock_settings:
            mock_settings.vault_uploads_dir.return_value = Path("/test/vault/1/uploads")

            provider = UploadPathProvider()
            result = provider.get_upload_dir(1)

            # EXACT VALUE ASSERTION
            assert result == Path("/test/vault/1/uploads")

            # CRITICAL: Verify only vault_uploads_dir was called (no DB-related calls)
            # The old implementation would have called get_pool or similar
            mock_settings.vault_uploads_dir.assert_called_once_with(1)

            # Verify no database-related methods were called
            # Since MagicMock auto-creates attributes, we check method_calls instead
            assert not any(
                "sqlite" in str(call) or "pool" in str(call) or "database" in str(call)
                for call in mock_settings.method_calls
            ), f"Unexpected database-related calls: {mock_settings.method_calls}"

    def test_get_upload_dir_with_different_vault_ids(self):
        """Test get_upload_dir correctly passes through different vault IDs."""
        with patch("app.services.upload_path.settings") as mock_settings:
            provider = UploadPathProvider()

            # Test vault_id=1
            mock_settings.vault_uploads_dir.return_value = Path("/vaults/1/uploads")
            result = provider.get_upload_dir(1)
            assert result == Path("/vaults/1/uploads")
            mock_settings.vault_uploads_dir.assert_called_with(1)

            # Test vault_id=999
            mock_settings.reset_mock()
            mock_settings.vault_uploads_dir.return_value = Path("/vaults/999/uploads")
            result = provider.get_upload_dir(999)
            assert result == Path("/vaults/999/uploads")
            mock_settings.vault_uploads_dir.assert_called_once_with(999)

    def test_get_vault_name_not_an_attribute(self):
        """Verify _get_vault_name is NOT an attribute of UploadPathProvider (was deleted)."""
        provider = UploadPathProvider()

        # CRITICAL: The old _get_vault_name method should NOT exist
        assert not hasattr(provider, "_get_vault_name"), (
            "_get_vault_name should have been deleted from UploadPathProvider"
        )

        # Also check the class doesn't have it as a method
        assert not hasattr(UploadPathProvider, "_get_vault_name"), (
            "_get_vault_name should have been deleted from UploadPathProvider class"
        )

    def test_no_private_vault_name_method(self):
        """Verify no private method for vault name lookup exists on the class."""
        # Get all methods/attributes that start with underscore
        private_attrs = [
            attr for attr in dir(UploadPathProvider) if attr.startswith("_")
        ]

        # Filter out dunder methods and dataclass defaults
        private_attrs = [a for a in private_attrs if not a.startswith("__")]

        # _get_vault_name should NOT be in the list
        assert "_get_vault_name" not in private_attrs, (
            "Found _get_vault_name in UploadPathProvider private attributes"
        )

    def test_get_upload_dir_direct_delegation(self):
        """Verify get_upload_dir is a thin wrapper around settings.vault_uploads_dir."""
        with patch("app.services.upload_path.settings") as mock_settings:
            # Set up the mock to return a specific path
            expected_path = Path("/data/vaults/123/uploads")
            mock_settings.vault_uploads_dir.return_value = expected_path

            provider = UploadPathProvider()
            result = provider.get_upload_dir(123)

            # The function should return exactly what settings.vault_uploads_dir returns
            # No transformation, no DB query, just direct delegation
            assert result == expected_path
            mock_settings.vault_uploads_dir.assert_called_once_with(123)

    def test_resolve_uses_get_upload_dir(self):
        """Verify resolve() correctly uses get_upload_dir to build paths."""
        with patch("app.services.upload_path.settings") as mock_settings:
            mock_settings.vault_uploads_dir.return_value = Path("/vaults/5/uploads")

            provider = UploadPathProvider()
            result = provider.resolve("document.pdf", 5)

            # EXACT VALUE: resolve should return get_upload_dir result + filename
            assert result == Path("/vaults/5/uploads/document.pdf")
            mock_settings.vault_uploads_dir.assert_called_with(5)

    def test_file_exists_uses_vault_id_path(self):
        """Verify file_exists checks the vault_id-based path, not querying DB."""
        with patch("app.services.upload_path.settings") as mock_settings:
            # Set up paths - file does NOT exist in new location
            mock_settings.vault_uploads_dir.return_value = Path("/vaults/1/uploads")
            mock_settings.uploads_dir = Path("/data/uploads")

            provider = UploadPathProvider()

            # The file doesn't exist (both locations don't have it)
            result = provider.file_exists("missing.pdf", 1)

            # Should return False without any DB call
            assert result is False
            # Only vault_uploads_dir should be called (no DB access)
            mock_settings.vault_uploads_dir.assert_called()

    def test_is_migrated_uses_vault_id_path(self):
        """Verify is_migrated uses vault_id path directly, no DB lookup."""
        with patch("app.services.upload_path.settings") as mock_settings:
            mock_settings.vault_uploads_dir.return_value = Path("/vaults/42/uploads")

            provider = UploadPathProvider()
            result = provider.is_migrated("test.pdf", 42)

            # Path doesn't exist on mocked filesystem, so should return False
            assert result is False
            mock_settings.vault_uploads_dir.assert_called_with(42)


class TestUploadPathProviderNoDBImport:
    """Tests verifying no database imports in UploadPathProvider."""

    def test_no_direct_database_import(self):
        """Verify UploadPathProvider module doesn't import database module at top level."""
        import app.services.upload_path as upload_module

        # Check that database module is not in the module's globals
        # (except for _lookup_vault_id which has a lazy import, but that's in migrate_uploads)
        top_level_imports = [
            name
            for name in dir(upload_module)
            if not name.startswith("_") or name == "_lookup_vault_id"
        ]

        # The UploadPathProvider class should not have any DB-related methods
        provider_methods = [
            attr
            for attr in dir(UploadPathProvider)
            if callable(getattr(UploadPathProvider, attr, None))
            and not attr.startswith("__")
        ]

        # Verify none of the provider methods are DB-related
        db_related = [
            m
            for m in provider_methods
            if "db" in m.lower() or "query" in m.lower() or "vault_name" in m.lower()
        ]
        assert db_related == [], f"Found unexpected DB-related methods: {db_related}"
