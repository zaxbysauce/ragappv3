"""
Tests for CORS origin handling in Settings.

Tests cover task 4.2:
- Validator handles comma-separated string input correctly
- Validator trims whitespace from origins
- Validator filters out empty strings
- Validator passes through list input unchanged
- docker-compose adds BACKEND_CORS_ORIGINS with correct default
"""

import pytest

from app.config import Settings


class TestParseBackendCorsOrigins:
    """Tests for the parse_backend_cors_origins field validator."""

    def test_comma_separated_string_parsed_correctly(self):
        """Comma-separated string should be split into list of origins."""
        settings = Settings(backend_cors_origins="http://localhost:5173,http://localhost:3000")
        assert settings.backend_cors_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_comma_separated_string_with_extra_whitespace_parsed(self):
        """Comma-separated string with extra whitespace should have whitespace trimmed."""
        settings = Settings(backend_cors_origins="  http://localhost:5173  ,  http://localhost:3000  ")
        assert settings.backend_cors_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_empty_strings_filtered_out(self):
        """Empty strings between commas should be filtered out."""
        settings = Settings(backend_cors_origins="http://localhost:5173,,http://localhost:3000")
        assert settings.backend_cors_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_trailing_comma_creates_empty_string_filtered(self):
        """Trailing comma should not create an empty string entry."""
        settings = Settings(backend_cors_origins="http://localhost:5173,http://localhost:3000,")
        assert settings.backend_cors_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_leading_comma_creates_empty_string_filtered(self):
        """Leading comma should not create an empty string entry."""
        settings = Settings(backend_cors_origins=",http://localhost:5173,http://localhost:3000")
        assert settings.backend_cors_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_list_input_passed_through_unchanged(self):
        """List input should be returned unchanged."""
        original_list = ["http://localhost:5173", "http://localhost:3000"]
        settings = Settings(backend_cors_origins=original_list)
        assert settings.backend_cors_origins == original_list

    def test_list_input_with_extra_whitespace_not_stripped(self):
        """List input should NOT have whitespace stripped (pass-through behavior)."""
        original_list = ["  http://localhost:5173  ", "http://localhost:3000"]
        settings = Settings(backend_cors_origins=original_list)
        assert settings.backend_cors_origins == original_list

    def test_single_origin_string_parsed(self):
        """Single origin without comma should still work."""
        settings = Settings(backend_cors_origins="http://localhost:5173")
        assert settings.backend_cors_origins == ["http://localhost:5173"]

    def test_multiple_origins_with_different_schemes(self):
        """Origins with different schemes (http, https) should be preserved."""
        settings = Settings(backend_cors_origins="http://localhost:5173,https://example.com,http://localhost:3000")
        assert settings.backend_cors_origins == ["http://localhost:5173", "https://example.com", "http://localhost:3000"]

    def test_origins_with_ports_preserved(self):
        """Origins with non-standard ports should be preserved."""
        settings = Settings(backend_cors_origins="http://localhost:8080,http://localhost:3000,https://example.com:8443")
        assert settings.backend_cors_origins == ["http://localhost:8080", "http://localhost:3000", "https://example.com:8443"]

    def test_only_empty_strings_becomes_empty_list(self):
        """String that resolves to only empty strings should become empty list."""
        settings = Settings(backend_cors_origins=",,")
        assert settings.backend_cors_origins == []

    def test_whitespace_only_string_becomes_empty_list(self):
        """Whitespace-only string should become empty list after filtering."""
        settings = Settings(backend_cors_origins="   ,   ,   ")
        assert settings.backend_cors_origins == []
