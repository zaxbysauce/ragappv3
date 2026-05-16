"""Verification tests for orphan_vault_id removal.

These tests verify that:
1. Settings object does not have orphan_vault_id property
2. _lookup_vault_id raises ValueError on failure (no orphan fallback)
3. migrate_uploads catches ValueError and skips the file
4. documents.py no longer references orphan_vault_id
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure app modules are imported from the project
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pytest

from app.config import Settings, settings


class TestOrphanVaultIdRemoval:
    """Tests verifying orphan_vault_id has been removed from the codebase."""

    def test_settings_has_no_orphan_vault_id_property(self):
        """Verify Settings class does not have orphan_vault_id attribute."""
        settings_obj = Settings()

        # orphan_vault_id should NOT exist on Settings instance
        assert not hasattr(settings_obj, "orphan_vault_id"), (
            "Settings should not have orphan_vault_id property - "
            "this property should have been removed"
        )

    def test_settings_orphan_vault_id_not_in_model_fields(self):
        """Verify orphan_vault_id is not defined in Settings model fields."""
        # Check it's not in the model fields
        model_fields = getattr(Settings, "model_fields", {})
        assert "orphan_vault_id" not in model_fields, (
            "orphan_vault_id should not be defined in Settings model_fields"
        )

    def test_settings_does_not_have_orphan_vault_id_class_attribute(self):
        """Verify orphan_vault_id is not a class attribute on Settings."""
        assert not hasattr(Settings, "orphan_vault_id"), (
            "Settings class should not have orphan_vault_id attribute"
        )


class TestLookupVaultIdRaisesValueError:
    """Tests verifying _lookup_vault_id raises ValueError without fallback."""

    def test_lookup_vault_id_raises_value_error_when_file_not_found(self):
        """Verify _lookup_vault_id raises ValueError when file not in database."""
        from app.services.upload_path import _lookup_vault_id

        # Create a mock pool that returns no results (file not found)
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_pool.get_connection.return_value = mock_conn

        # get_pool is imported inside the function, so patch where it's used
        with patch("app.models.database.get_pool", return_value=mock_pool):
            with patch("app.services.upload_path.settings") as mock_settings:
                mock_settings.sqlite_path = ":memory:"

                # Should raise ValueError, not return orphan_vault_id
                with pytest.raises(ValueError) as exc_info:
                    _lookup_vault_id("nonexistent_file.txt")

                assert "Could not determine vault_id" in str(exc_info.value)

    def test_lookup_vault_id_does_not_fallback_to_orphan_vault_id(self):
        """Verify _lookup_vault_id does NOT fall back to orphan_vault_id."""
        from app.services.upload_path import _lookup_vault_id

        # Create a mock pool that returns no results
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_pool.get_connection.return_value = mock_conn

        # get_pool is imported inside the function, so patch where it's used
        with patch("app.models.database.get_pool", return_value=mock_pool):
            with patch("app.services.upload_path.settings") as mock_settings:
                mock_settings.sqlite_path = ":memory:"

                # Even if orphan_vault_id was set (which it shouldn't be),
                # _lookup_vault_id should raise ValueError, not return it
                try:
                    result = _lookup_vault_id("nonexistent_file.txt")
                    # If we get here, the function returned a value instead of raising
                    assert False, (
                        f"_lookup_vault_id should raise ValueError, "
                        f"but returned {result}"
                    )
                except ValueError:
                    pass  # Expected behavior - no orphan fallback


class TestMigrateUploadsCatchesValueError:
    """Tests verifying migrate_uploads catches ValueError and skips files."""

    def test_migrate_uploads_catches_value_error(self):
        """Verify migrate_uploads catches ValueError from _lookup_vault_id."""
        from app.services.upload_path import migrate_uploads

        # Create a temporary directory with a file
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file in what looks like the old uploads dir
            old_uploads = Path(tmpdir) / "old_uploads"
            old_uploads.mkdir()
            test_file = old_uploads / "orphan_file.txt"
            test_file.write_text("test content")

            mock_pool = MagicMock()
            mock_conn = MagicMock()
            # Return None to simulate file not found in database
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_pool.get_connection.return_value = mock_conn

            with patch("app.services.upload_path.settings") as mock_settings:
                mock_settings.uploads_dir = old_uploads
                mock_settings.sqlite_path = ":memory:"

                # get_pool is imported inside _lookup_vault_id function
                with patch("app.models.database.get_pool", return_value=mock_pool):
                    result = migrate_uploads(dry_run=False)

                    # File should be in failed list because ValueError was raised
                    assert "orphan_file.txt" in result.failed, (
                        "File should be in failed list when _lookup_vault_id raises ValueError"
                    )


class TestDocumentsNoOrphanReference:
    """Tests verifying documents.py does not reference orphan_vault_id."""

    def test_documents_route_uses_vault_id_directly(self):
        """Verify documents.py upload uses vault_id without orphan fallback."""
        # Read the documents.py source file and verify it doesn't contain orphan_vault_id
        documents_path = Path(__file__).parent.parent / "app" / "api" / "routes" / "documents.py"

        if documents_path.exists():
            content = documents_path.read_text()

            # Should NOT contain orphan_vault_id reference
            assert "orphan_vault_id" not in content, (
                "documents.py should not reference orphan_vault_id - "
                "upload should use vault_id directly"
            )

            # Should NOT contain the pattern: vault_id or settings.orphan_vault_id
            assert "vault_id or settings.orphan_vault_id" not in content, (
                "documents.py should not use 'vault_id or settings.orphan_vault_id' fallback"
            )

    def test_upload_path_no_orphan_reference(self):
        """Verify upload_path.py does not reference orphan_vault_id."""
        upload_path_path = Path(__file__).parent.parent / "app" / "services" / "upload_path.py"

        if upload_path_path.exists():
            content = upload_path_path.read_text()

            # _lookup_vault_id should NOT reference orphan_vault_id
            assert "orphan_vault_id" not in content, (
                "upload_path.py should not reference orphan_vault_id"
            )


class TestConfigNoOrphanReference:
    """Tests verifying config.py does not define orphan_vault_id."""

    def test_config_no_orphan_vault_id_definition(self):
        """Verify config.py does not define orphan_vault_id."""
        config_path = Path(__file__).parent.parent / "app" / "config.py"

        if config_path.exists():
            content = config_path.read_text()

            # Should NOT define orphan_vault_id
            assert "orphan_vault_id" not in content, (
                "config.py should not define orphan_vault_id"
            )
