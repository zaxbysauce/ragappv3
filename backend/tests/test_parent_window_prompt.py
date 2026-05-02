"""Tests for parent-window prompt rendering and safe legacy fallback (P3.2)."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.services.document_retrieval import RAGSource
from app.services.prompt_builder import PromptBuilderService


def _make_chunk(text: str, parent_window: str = None, raw_text: str = None) -> RAGSource:
    src = RAGSource(
        text=text,
        file_id="f1",
        score=0.1,
        metadata={"filename": "doc.pdf"},
    )
    if raw_text is not None:
        src.metadata["raw_text"] = raw_text
    if parent_window is not None:
        src.parent_window_text = parent_window
    return src


class TestParentWindowRendering(unittest.TestCase):
    def setUp(self):
        self._orig = settings.parent_retrieval_enabled
        settings.parent_retrieval_enabled = True

    def tearDown(self):
        settings.parent_retrieval_enabled = self._orig

    def test_parent_window_renders_match_markers(self):
        """When parent_window_text is present, the matched chunk text is
        bracketed with ``[[MATCH: …]]`` so the LLM can orient on the exact
        evidence within a wider window.
        """
        builder = PromptBuilderService()
        match_text = "Jane signed the contract on 2024-01-15."
        parent = (
            "Earlier on the page, the parties were introduced. "
            f"{match_text} "
            "Subsequent paragraphs detail enforcement clauses."
        )
        chunk = _make_chunk(text=match_text, parent_window=parent, raw_text=match_text)

        formatted = builder.format_chunk(chunk, source_index=1)
        self.assertIn(f"[[MATCH: {match_text}]]", formatted)
        # Surrounding context must still appear in the rendered chunk.
        self.assertIn("Earlier on the page", formatted)
        self.assertIn("enforcement clauses", formatted)
        # Source label still attaches.
        self.assertIn("[S1]", formatted)

    def test_chunk_without_parent_window_degrades_safely(self):
        """Legacy chunks (no stored parent window) must still render — the
        prompt builder falls back to the small chunk text alone.
        """
        builder = PromptBuilderService()
        chunk = _make_chunk(text="legacy chunk body", parent_window=None)

        formatted = builder.format_chunk(chunk, source_index=2)
        self.assertIn("[S2]", formatted)
        self.assertIn("legacy chunk body", formatted)
        # No MATCH markers when no parent window is available.
        self.assertNotIn("[[MATCH:", formatted)

    def test_parent_window_off_renders_chunk_only(self):
        """With the feature flag off, parent_window_text is ignored even when present."""
        settings.parent_retrieval_enabled = False
        try:
            builder = PromptBuilderService()
            chunk = _make_chunk(
                text="match body",
                parent_window="surrounding context with match body inside",
                raw_text="match body",
            )
            formatted = builder.format_chunk(chunk, source_index=1)
            self.assertNotIn("[[MATCH:", formatted)
            self.assertIn("match body", formatted)
            self.assertNotIn("surrounding context", formatted)
        finally:
            settings.parent_retrieval_enabled = True


if __name__ == "__main__":
    unittest.main()
