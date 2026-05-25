"""Tests for document content-level (parsed_text body) search.

Phase 1.5: ``files_content_fts`` indexes ``files.parsed_text`` so the document
list search matches document *body* text, not just filename/metadata. These
tests verify the end-to-end route behaviour against a real SQLite FTS index.
"""

from test_documents_auth import TestDocumentAuthBase


class TestDocumentContentSearch(TestDocumentAuthBase):
    """GET /documents?search=... matches parsed_text body content."""

    def _seed_doc(self, file_id, vault_id, file_name, parsed_text):
        conn = self._connection_pool.get_connection()
        try:
            conn.execute(
                "INSERT INTO files (id, file_name, file_path, file_size, status, "
                "chunk_count, vault_id, parsed_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    file_name,
                    f"/uploads/{file_name}",
                    100,
                    "indexed",
                    1,
                    vault_id,
                    parsed_text,
                ),
            )
            conn.commit()
        finally:
            self._connection_pool.release_connection(conn)

    def test_search_matches_body_text_not_in_metadata(self):
        # Body contains a unique token absent from the filename/metadata.
        self._seed_doc(
            100, 2, "quarterly_report.txt", "Revenue grew because of zlorptanium sales."
        )
        token = self._member_token()  # member1 has write/read on vault 2
        resp = self.client.get(
            "/api/documents?vault_id=2&search=zlorptanium",
            headers=self._auth_headers(token),
        )
        self.assertEqual(resp.status_code, 200)
        names = [d["file_name"] for d in resp.json()["documents"]]
        self.assertIn("quarterly_report.txt", names)

    def test_search_non_matching_token_excludes_doc(self):
        self._seed_doc(
            101, 2, "quarterly_report.txt", "Revenue grew because of zlorptanium sales."
        )
        token = self._member_token()
        resp = self.client.get(
            "/api/documents?vault_id=2&search=nonexistentword",
            headers=self._auth_headers(token),
        )
        self.assertEqual(resp.status_code, 200)
        names = [d["file_name"] for d in resp.json()["documents"]]
        self.assertNotIn("quarterly_report.txt", names)

    def test_filename_search_still_works(self):
        # Regression: metadata/filename search path is unaffected.
        self._seed_doc(102, 2, "budget_plan.txt", "Some unrelated body content here.")
        token = self._member_token()
        resp = self.client.get(
            "/api/documents?vault_id=2&search=budget",
            headers=self._auth_headers(token),
        )
        self.assertEqual(resp.status_code, 200)
        names = [d["file_name"] for d in resp.json()["documents"]]
        self.assertIn("budget_plan.txt", names)

    def test_fts_trigger_guard_metadata_update_does_not_reindex(self):
        """UPDATE trigger WHEN guard: updating status/file_name without changing
        parsed_text must NOT re-insert a row into files_content_fts.

        Verifies the key optimization in the trigger definition:
            WHEN new.parsed_text IS NOT old.parsed_text
        so frequent metadata/progress writes during ingestion are cheap.
        """
        self._seed_doc(
            103, 2, "trigger_guard.txt", "unique_trigger_token_xyz"
        )
        conn = self._connection_pool.get_connection()
        try:
            # Count FTS rows for this doc before the metadata update.
            before = conn.execute(
                "SELECT COUNT(*) FROM files_content_fts WHERE files_content_fts MATCH ?",
                ("unique_trigger_token_xyz",),
            ).fetchone()[0]
            self.assertEqual(before, 1, "FTS row must exist after insert")

            # Update metadata only — do NOT change parsed_text.
            # Must use a valid status value (CHECK constraint: pending, processing,
            # indexed, error).
            conn.execute(
                "UPDATE files SET status = 'error' WHERE id = 103"
            )
            conn.commit()

            after = conn.execute(
                "SELECT COUNT(*) FROM files_content_fts WHERE files_content_fts MATCH ?",
                ("unique_trigger_token_xyz",),
            ).fetchone()[0]
        finally:
            self._connection_pool.release_connection(conn)

        self.assertEqual(
            after,
            before,
            "FTS row count must be unchanged after metadata-only UPDATE",
        )

    def test_content_search_vault_isolation(self):
        """Content FTS subquery must not leak documents across vaults.

        Seeds a doc with a unique token in vault 1 (admin vault). Searching
        vault 2 for that token must return no results, proving vault scoping
        is enforced at the subquery level, not just the outer WHERE.
        """
        # Seed into vault 3 ("Read-Only Vault" in test setup — member1 has no
        # write access, but it exists and satisfies FK constraints).
        conn = self._connection_pool.get_connection()
        try:
            conn.execute(
                "INSERT INTO files (id, file_name, file_path, file_size, status, "
                "chunk_count, vault_id, parsed_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    104,
                    "vault3_secret.txt",
                    "/uploads/vault3_secret.txt",
                    100,
                    "indexed",
                    1,
                    3,  # vault 3 — different from vault 2
                    "xqztoken_vault_isolation_probe",
                ),
            )
            conn.commit()
        finally:
            self._connection_pool.release_connection(conn)

        # member1 has read on vault 2 — search vault 2 for the vault-3 token.
        token = self._member_token()
        resp = self.client.get(
            "/api/documents?vault_id=2&search=xqztoken_vault_isolation_probe",
            headers=self._auth_headers(token),
        )
        self.assertEqual(resp.status_code, 200)
        names = [d["file_name"] for d in resp.json()["documents"]]
        self.assertNotIn(
            "vault3_secret.txt",
            names,
            "Cross-vault content FTS leak: vault 3 doc appeared in vault 2 results",
        )
