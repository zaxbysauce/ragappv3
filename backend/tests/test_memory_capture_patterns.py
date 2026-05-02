"""Tests for deterministic memory capture (P2.5)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.memory_store import MemoryStore


class TestMemoryCapture(unittest.TestCase):
    def setUp(self) -> None:
        # detect_memory_intent is pure regex — no DB needed.
        self.store = MemoryStore.__new__(MemoryStore)

    def test_remember_that(self):
        self.assertEqual(
            self.store.detect_memory_intent(
                "Please remember that I prefer concise reports."
            ),
            "I prefer concise reports",
        )

    def test_remember_to(self):
        self.assertEqual(
            self.store.detect_memory_intent("Remember to cite all sources."),
            "cite all sources",
        )

    def test_dont_forget_with_apostrophe(self):
        self.assertEqual(
            self.store.detect_memory_intent("Don't forget to attach the appendix."),
            "to attach the appendix",
        )

    def test_keep_in_mind(self):
        self.assertEqual(
            self.store.detect_memory_intent(
                "Keep in mind that deadlines slip on Mondays."
            ),
            "deadlines slip on Mondays",
        )

    def test_save_as_memory(self):
        self.assertEqual(
            self.store.detect_memory_intent(
                "Save as memory: the API rate limit is 100/min"
            ),
            "the API rate limit is 100/min",
        )

    def test_my_preference_is(self):
        self.assertEqual(
            self.store.detect_memory_intent(
                "My preference is that all reports are source-backed."
            ),
            "all reports are source-backed",
        )

    def test_trailing_punctuation_handled(self):
        self.assertEqual(
            self.store.detect_memory_intent("Remember to ship on Monday!"),
            "ship on Monday",
        )
        self.assertEqual(
            self.store.detect_memory_intent("Remember that I dislike PDFs?"),
            "I dislike PDFs",
        )

    def test_no_match_for_plain_text(self):
        self.assertIsNone(
            self.store.detect_memory_intent("What is the deadline for the project?")
        )

    def test_quote_guard_suppresses_embedded_note(self):
        # "note that" appears inside a quoted document description — the
        # quote-guard should suppress capture so we don't store random
        # document fragments as memories.
        self.assertIsNone(
            self.store.detect_memory_intent(
                'According to the document: "note that the API has rate limits".'
            )
        )

    def test_imperative_note_that_still_matches(self):
        self.assertEqual(
            self.store.detect_memory_intent(
                "Note that I work in PST and prefer afternoon meetings."
            ),
            "I work in PST and prefer afternoon meetings",
        )

    def test_empty_input(self):
        self.assertIsNone(self.store.detect_memory_intent(""))
        self.assertIsNone(self.store.detect_memory_intent("   "))
        self.assertIsNone(self.store.detect_memory_intent(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
