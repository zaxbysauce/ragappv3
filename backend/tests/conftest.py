"""Test environment configuration.

Uses pytest_configure hook to set test-compatible environment variables
and clear all app.* modules from sys.modules before test collection.
This ensures settings are initialized with test-compatible values every time.
"""

import os


def pytest_configure(config):
    """Called before test collection.

    Sets environment variables and clears all app.* modules from the
    import cache so they re-import with test-compatible settings.
    """
    os.environ["ADMIN_SECRET_TOKEN"] = "test-admin-key"
    os.environ["USERS_ENABLED"] = "false"
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing-only"

    import sys

    app_keys = [
        k for k in list(sys.modules.keys()) if k == "app" or k.startswith("app.")
    ]
    for key in app_keys:
        del sys.modules[key]


# Also clean up diagnostic file if it was created by a previous version
import pathlib

diag_file = pathlib.Path(__file__).parent / "_conftest_diag.txt"
if diag_file.exists():
    diag_file.unlink(missing_ok=True)
