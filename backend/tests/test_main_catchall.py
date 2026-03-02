"""
Tests for main.py catch-all route functionality - simplified version.
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest


class TestMainCatchAllRoute(unittest.TestCase):
    """Test suite for catch-all route in main.py."""

    def test_fileresponse_import_present(self):
        """Test that FileResponse is imported in main.py."""
        # Read the main.py file and check for FileResponse import
        main_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'main.py')
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Check for FileResponse import (can be with other imports)
        self.assertIn('FileResponse', content,
                      "FileResponse import not found in main.py")

    def test_catchall_route_registered(self):
        """Test that catch-all route is registered for unmatched paths."""
        main_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'main.py')
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Check for catch-all route definition
        self.assertIn('@app.get("/{full_path:path}")', content,
                      "Catch-all route decorator not found in main.py")
        self.assertIn('async def serve_spa(full_path: str):', content,
                      "serve_spa function not found in main.py")

    def test_catchall_serves_index_html(self):
        """Test that catch-all route serves index.html."""
        main_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'main.py')
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Check that serve_spa returns FileResponse with index.html
        self.assertIn('FileResponse(str(static_dir / "index.html"))', content,
                      "serve_spa does not return FileResponse with index.html")

    def test_catchall_route_position(self):
        """Test that catch-all route is defined after other routes."""
        main_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'main.py')
        with open(main_file, 'r') as f:
            lines = f.readlines()
        
        # Find line numbers for key elements
        catchall_line = None
        last_router_line = None
        
        for i, line in enumerate(lines):
            if '@app.get("/{full_path:path}")' in line:
                catchall_line = i
            if 'app.include_router' in line:
                last_router_line = i
        
        self.assertIsNotNone(catchall_line, "Catch-all route not found")
        self.assertIsNotNone(last_router_line, "No routers found")
        self.assertTrue(catchall_line > last_router_line,
                        "Catch-all route should be defined after all routers")


if __name__ == "__main__":
    unittest.main()
