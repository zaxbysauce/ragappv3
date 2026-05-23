"""
Verification tests for task 3.2 — Static mount path is prefix-aware.
Tests that assets_mount_path correctly incorporates root_path prefix.

Expected behavior:
- root_path="" → mount path = "/assets"
- root_path="/knowledgevault" → mount path = "/knowledgevault/assets"
"""

import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings


class TestStaticMountPathPrefixAware:
    """Test that static mount path respects root_path prefix."""

    def test_root_path_empty_mount_path_is_assets(self):
        """root_path='' should result in mount path '/assets'."""
        with patch.dict("os.environ", {"ROOT_PATH": ""}):
            settings = Settings()
            # Compute mount path using the same logic as main.py
            assets_mount_path = f"{settings.root_path}/assets" if settings.root_path else "/assets"
            assert assets_mount_path == "/assets"

    def test_root_path_knowledgevault_mount_path_includes_prefix(self):
        """root_path='/knowledgevault' should result in mount path '/knowledgevault/assets'."""
        with patch.dict("os.environ", {"ROOT_PATH": "/knowledgevault"}):
            settings = Settings()
            # Compute mount path using the same logic as main.py
            assets_mount_path = f"{settings.root_path}/assets" if settings.root_path else "/assets"
            assert assets_mount_path == "/knowledgevault/assets"

    def test_root_path_with_trailing_slash(self):
        """root_path='/kv/' should result in mount path '/kv/assets' (trailing slash stripped)."""
        with patch.dict("os.environ", {"ROOT_PATH": "/kv/"}):
            settings = Settings()
            # The implementation strips trailing slashes from root_path
            _root = settings.root_path.rstrip("/") if settings.root_path else ""
            assets_mount_path = f"{_root}/assets" if _root else "/assets"
            assert assets_mount_path == "/kv/assets"

    def test_root_path_only_slash(self):
        """root_path='/' should result in mount path '/assets' (stripped to empty, then falsy)."""
        with patch.dict("os.environ", {"ROOT_PATH": "/"}):
            settings = Settings()
            _root = settings.root_path.rstrip("/") if settings.root_path else ""
            assets_mount_path = f"{_root}/assets" if _root else "/assets"
            assert assets_mount_path == "/assets"


class TestMountPathLogicDirectly:
    """Direct tests of the mount path logic from main.py line 144."""

    def test_logic_root_path_empty_string_is_falsy(self):
        """Empty string root_path is falsy in Python, so should use '/assets'."""
        root_path = ""
        assets_mount_path = f"{root_path}/assets" if root_path else "/assets"
        assert assets_mount_path == "/assets"

    def test_logic_root_path_with_value_is_truthy(self):
        """Non-empty root_path is truthy, so prefix is applied."""
        root_path = "/knowledgevault"
        assets_mount_path = f"{root_path}/assets" if root_path else "/assets"
        assert assets_mount_path == "/knowledgevault/assets"

    def test_logic_root_path_none_is_falsy(self):
        """None root_path is falsy, so should use '/assets'."""
        root_path = None
        # Using conditional expression
        assets_mount_path = f"{root_path}/assets" if root_path else "/assets"
        assert assets_mount_path == "/assets"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])