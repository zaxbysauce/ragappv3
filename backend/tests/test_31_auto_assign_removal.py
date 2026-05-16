"""Tests for 3.1: _auto_assign_user_to_defaults removal.

Verifies that the _auto_assign_user_to_defaults function has been fully removed
from both users.py and auth.py, including all call sites.
"""

import re
from pathlib import Path

import pytest

_ROUTES = Path(__file__).resolve().parents[1] / "app" / "api" / "routes"
USERS_PY = str(_ROUTES / "users.py")
AUTH_PY = str(_ROUTES / "auth.py")


class TestAutoAssignUserToDefaultsRemoval:
    """Regression tests for _auto_assign_user_to_defaults removal (3.1)."""

    def test_users_py_does_not_contain_auto_assign_user_to_defaults_definition(self):
        """users.py must not contain any _auto_assign_user_to_defaults function definition."""
        content = open(USERS_PY, encoding="utf-8").read()
        pattern = re.compile(r"def\s+_auto_assign_user_to_defaults\s*\(", re.MULTILINE)
        match = pattern.search(content)
        assert match is None, (
            f"users.py still contains _auto_assign_user_to_defaults function definition at position {match.start() if match else 'N/A'}. "
            "The function definition must be removed."
        )

    def test_auth_py_does_not_import_auto_assign_user_to_defaults(self):
        """auth.py must not import _auto_assign_user_to_defaults from any module."""
        content = open(AUTH_PY, encoding="utf-8").read()
        pattern = re.compile(r"from\s+\S+\s+import\s+.*_auto_assign_user_to_defaults", re.MULTILINE)
        match = pattern.search(content)
        assert match is None, (
            f"auth.py imports _auto_assign_user_to_defaults. Import must be removed. Match: {match.group() if match else 'N/A'}"
        )

    def test_auth_py_does_not_call_auto_assign_user_to_defaults(self):
        """auth.py must not call _auto_assign_user_to_defaults anywhere."""
        content = open(AUTH_PY, encoding="utf-8").read()
        pattern = re.compile(r"_auto_assign_user_to_defaults\s*\(", re.MULTILINE)
        match = pattern.search(content)
        assert match is None, (
            f"auth.py calls _auto_assign_user_to_defaults. All call sites must be removed. Match: {match.group() if match else 'N/A'}"
        )

    def test_create_user_in_users_py_does_not_call_auto_assign_user_to_defaults(self):
        """create_user in users.py must not call _auto_assign_user_to_defaults."""
        content = open(USERS_PY, encoding="utf-8").read()

        # Extract the create_user function body
        create_user_match = re.search(
            r"(async\s+)?def\s+create_user\s*\([^)]*\).*?(?=\n(?:@router|async\s+def\s|def\s|\Z))",
            content,
            re.DOTALL | re.MULTILINE,
        )
        assert create_user_match is not None, "create_user function not found in users.py"
        create_user_body = create_user_match.group()

        pattern = re.compile(r"_auto_assign_user_to_defaults\s*\(", re.MULTILINE)
        match = pattern.search(create_user_body)
        assert match is None, (
            "create_user in users.py still calls _auto_assign_user_to_defaults. "
            "All call sites within create_user must be removed."
        )

    def test_no_auto_assign_user_to_defaults_anywhere_in_users_py(self):
        """users.py must not contain _auto_assign_user_to_defaults at all (definition, import, or call)."""
        content = open(USERS_PY, encoding="utf-8").read()
        pattern = re.compile(r"_auto_assign_user_to_defaults")
        matches = list(pattern.finditer(content))
        assert len(matches) == 0, (
            f"users.py contains {len(matches)} occurrence(s) of _auto_assign_user_to_defaults. "
            "The function must be fully removed."
        )

    def test_no_auto_assign_user_to_defaults_anywhere_in_auth_py(self):
        """auth.py must not contain _auto_assign_user_to_defaults at all (definition, import, or call)."""
        content = open(AUTH_PY, encoding="utf-8").read()
        pattern = re.compile(r"_auto_assign_user_to_defaults")
        matches = list(pattern.finditer(content))
        assert len(matches) == 0, (
            f"auth.py contains {len(matches)} occurrence(s) of _auto_assign_user_to_defaults. "
            "The function must be fully removed."
        )
