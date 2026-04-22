"""Unit tests for maintenance service with system_flags table."""

import os
import sqlite3
import sys
import tempfile
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.database import SQLiteConnectionPool, init_db
from app.services.maintenance import MaintenanceService


class TestMaintenanceService(unittest.TestCase):
    """Test cases for MaintenanceService with system_flags table."""

    def setUp(self):
        """Create a temporary database file for each test."""
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.temp_fd)
        self.pool = SQLiteConnectionPool(self.temp_db_path, max_size=2)

    def tearDown(self):
        """Clean up the temporary database file."""
        self.pool.close_all()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_init_db_creates_system_flags_table(self):
        """Test that init_db creates system_flags table."""
        # Initialize the database
        init_db(self.temp_db_path)

        # Connect and check for system_flags table
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table') AND name = 'system_flags'"
        )
        result = cursor.fetchone()
        conn.close()

        # Assert system_flags table exists
        self.assertIsNotNone(result, "system_flags table was not created by init_db()")
        self.assertEqual(result[0], 'system_flags')

    def test_maintenance_service_initialization(self):
        """Test MaintenanceService initializes correctly."""
        init_db(self.temp_db_path)
        MaintenanceService(self.pool)

        # Check that maintenance flag row was created
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value, reason FROM system_flags WHERE name = 'maintenance'")
        result = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(result, "maintenance flag row was not created")
        self.assertEqual(result[0], 'maintenance')
        self.assertEqual(result[1], 0)  # Should default to 0 (disabled)
        self.assertEqual(result[2], '')  # Should default to empty reason

    def test_get_flag_returns_disabled_by_default(self):
        """Test that get_flag returns disabled state by default."""
        init_db(self.temp_db_path)
        service = MaintenanceService(self.pool)

        flag = service.get_flag()

        self.assertFalse(flag.enabled)
        self.assertEqual(flag.reason, "")
        self.assertEqual(flag.version, 0)

    def test_set_flag_enables_maintenance(self):
        """Test that set_flag can enable maintenance mode."""
        init_db(self.temp_db_path)
        service = MaintenanceService(self.pool)

        service.set_flag(True, "Scheduled maintenance")
        flag = service.get_flag()

        self.assertTrue(flag.enabled)
        self.assertEqual(flag.reason, "Scheduled maintenance")
        self.assertEqual(flag.version, 1)  # Version should increment

    def test_set_flag_disables_maintenance(self):
        """Test that set_flag can disable maintenance mode."""
        init_db(self.temp_db_path)
        service = MaintenanceService(self.pool)

        # First enable
        service.set_flag(True, "Scheduled maintenance")
        flag = service.get_flag()
        self.assertTrue(flag.enabled)

        # Then disable
        service.set_flag(False, "Maintenance complete")
        flag = service.get_flag()

        self.assertFalse(flag.enabled)
        self.assertEqual(flag.reason, "Maintenance complete")
        self.assertEqual(flag.version, 2)  # Version should increment again

    def test_set_flag_updates_version_correctly(self):
        """Test that set_flag increments version on each update."""
        init_db(self.temp_db_path)
        service = MaintenanceService(self.pool)

        flag1 = service.get_flag()
        self.assertEqual(flag1.version, 0)

        service.set_flag(True, "First update")
        flag2 = service.get_flag()
        self.assertEqual(flag2.version, 1)

        service.set_flag(False, "Second update")
        flag3 = service.get_flag()
        self.assertEqual(flag3.version, 2)

        service.set_flag(True, "Third update")
        flag4 = service.get_flag()
        self.assertEqual(flag4.version, 3)

    def test_get_flag_returns_updated_at(self):
        """Test that get_flag returns the updated_at timestamp."""
        init_db(self.temp_db_path)
        service = MaintenanceService(self.pool)

        # Initial flag should have updated_at
        flag1 = service.get_flag()
        self.assertIsNotNone(flag1.updated_at)

        # After update, updated_at should be present
        service.set_flag(True, "Update")
        flag2 = service.get_flag()
        self.assertIsNotNone(flag2.updated_at)

    def test_set_flag_with_empty_reason(self):
        """Test that set_flag works with empty reason."""
        init_db(self.temp_db_path)
        service = MaintenanceService(self.pool)

        service.set_flag(True)
        flag = service.get_flag()

        self.assertTrue(flag.enabled)
        self.assertEqual(flag.reason, "")

    def test_multiple_service_instances_share_same_database(self):
        """Test that multiple MaintenanceService instances share the same database state."""
        init_db(self.temp_db_path)

        service1 = MaintenanceService(self.pool)
        service2 = MaintenanceService(self.pool)

        # Set flag via service1
        service1.set_flag(True, "Set by service1")

        # Read via service2
        flag = service2.get_flag()

        self.assertTrue(flag.enabled)
        self.assertEqual(flag.reason, "Set by service1")


if __name__ == '__main__':
    unittest.main()
