"""Tests for the new vault read-access checks on memory list/search routes.

Covers:
- GET /memories with vault_id requires read access on that vault.
- POST /memories/search with vault_id requires read access.
- GET /memories/search with vault_id requires read access.
- vault_id omitted is restricted to admin/superadmin.
"""

import os
import sys
import unittest
from unittest.mock import patch

# Reuse the existing test scaffolding (TestMemoriesAuthBase).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_memories_auth import TestMemoriesAuthBase  # type: ignore


class TestMemoriesListAuthz(TestMemoriesAuthBase):
    def test_get_memories_member_without_vault_access_returns_403(self):
        # member2 (user 4) has no access to vault 2.
        response = self.client.get(
            "/api/memories?vault_id=2",
            headers=self._auth_headers(self._member_no_access_token()),
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("No read access", response.json().get("detail", ""))

    def test_get_memories_member_with_vault_access_succeeds(self):
        # member1 (user 3) has write access to vault 2 → read access implied.
        response = self.client.get(
            "/api/memories?vault_id=2",
            headers=self._auth_headers(self._member_token()),
        )
        self.assertEqual(response.status_code, 200)

    def test_get_memories_no_vault_id_member_blocked(self):
        # No vault_id → broad listing → admin-only.
        response = self.client.get(
            "/api/memories",
            headers=self._auth_headers(self._member_token()),
        )
        self.assertEqual(response.status_code, 403)

    def test_get_memories_no_vault_id_admin_succeeds(self):
        response = self.client.get(
            "/api/memories",
            headers=self._auth_headers(self._admin_token()),
        )
        self.assertEqual(response.status_code, 200)


class TestMemoriesSearchAuthz(TestMemoriesAuthBase):
    def test_post_search_unauthorized_vault(self):
        response = self.client.post(
            "/api/memories/search",
            json={"query": "anything", "vault_id": 2},
            headers=self._auth_headers(self._member_no_access_token()),
        )
        self.assertEqual(response.status_code, 403)

    def test_post_search_authorized_vault(self):
        # We need to make _perform_memory_search return an empty list rather
        # than hit FTS — the mock_memory_store from the base class doesn't
        # define search_memories. Patch it for this test.
        self._mock_memory_store.search_memories = lambda *a, **k: []
        response = self.client.post(
            "/api/memories/search",
            json={"query": "anything", "vault_id": 2},
            headers=self._auth_headers(self._member_token()),
        )
        self.assertEqual(response.status_code, 200)

    def test_get_search_unauthorized_vault(self):
        response = self.client.get(
            "/api/memories/search?query=any&vault_id=2",
            headers=self._auth_headers(self._member_no_access_token()),
        )
        self.assertEqual(response.status_code, 403)

    def test_get_search_no_vault_id_blocked_for_member(self):
        response = self.client.get(
            "/api/memories/search?query=any",
            headers=self._auth_headers(self._member_token()),
        )
        self.assertEqual(response.status_code, 403)

    def test_get_search_no_vault_id_admin_ok(self):
        self._mock_memory_store.search_memories = lambda *a, **k: []
        response = self.client.get(
            "/api/memories/search?query=any",
            headers=self._auth_headers(self._admin_token()),
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
