"""Tests for upload path provider and migration."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from app.services.upload_path import MigrationResult, UploadPathProvider


class TestUploadPathProvider:
    """Tests for UploadPathProvider."""

    @patch("app.services.upload_path.settings")
    def test_get_upload_dir(self, mock_settings):
        """Test vault-specific directory generation."""
        mock_settings.vaults_dir = Path("/data/vaults")

        provider = UploadPathProvider()
        result = provider.get_upload_dir(5)

        assert result == Path("/data/vaults/5/uploads")

    @patch("app.services.upload_path.settings")
    def test_resolve(self, mock_settings):
        """Test file path resolution."""
        mock_settings.vaults_dir = Path("/data/vaults")

        provider = UploadPathProvider()
        result = provider.resolve("test.pdf", 3)

        assert result == Path("/data/vaults/3/uploads/test.pdf")

    @patch("app.services.upload_path.settings")
    def test_get_legacy(self, mock_settings):
        """Test legacy path fallback."""
        mock_settings.uploads_dir = Path("/data/uploads")

        provider = UploadPathProvider()
        result = provider.get_legacy("test.pdf")

        assert result == Path("/data/uploads/test.pdf")

    @patch("app.services.upload_path.settings")
    def test_orphan_vault_id_fallback(self, mock_settings):
        """Test orphan vault ID configuration."""
        mock_settings.orphan_vault_id = 1
        mock_settings.vaults_dir = Path("/data/vaults")

        provider = UploadPathProvider()

        # Test that is_migrated returns False when file doesn't exist
        # (since we're not actually creating files on disk in unit tests)
        result = provider.is_migrated("test.pdf", 1)
        assert not result

        # Test that resolve returns correct path for vault_id=1
        result = provider.resolve("test.pdf", 1)
        assert result == Path("/data/vaults/1/uploads/test.pdf")


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_creation(self):
        """Test MigrationResult creation."""
        result = MigrationResult(
            total=10,
            migrated=8,
            failed=["file1.pdf", "file2.pdf"],
            can_rollback=True
        )

        assert result.total == 10
        assert result.migrated == 8
        assert len(result.failed) == 2
        assert result.can_rollback
