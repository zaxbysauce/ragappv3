"""Tests for conditional query transformation.

Validates that:
- Exact/quoted queries bypass step-back/HyDE
- Filename-specific queries bypass transformation
- Short exact lookups bypass transformation
- Abstract conceptual queries still get transformed
"""

import unittest
from app.services.query_transformer import _is_exact_or_document_query


class TestQueryTypeDetection(unittest.TestCase):
    """Test _is_exact_or_document_query detection logic."""

    def test_quoted_phrase_is_exact(self):
        self.assertTrue(_is_exact_or_document_query('What is "machine learning"?'))

    def test_filename_pdf_is_exact(self):
        self.assertTrue(_is_exact_or_document_query("What does report.pdf say?"))

    def test_filename_docx_is_exact(self):
        self.assertTrue(_is_exact_or_document_query("summary from config.yaml"))

    def test_filename_md_is_exact(self):
        self.assertTrue(_is_exact_or_document_query("README.md contents"))

    def test_short_lookup_is_exact(self):
        self.assertTrue(_is_exact_or_document_query("API key"))

    def test_single_word_is_exact(self):
        self.assertTrue(_is_exact_or_document_query("authentication"))

    def test_conceptual_question_is_not_exact(self):
        self.assertFalse(
            _is_exact_or_document_query(
                "How does the authentication system handle token refresh?"
            )
        )

    def test_abstract_query_is_not_exact(self):
        self.assertFalse(
            _is_exact_or_document_query(
                "Explain the architecture of the retrieval pipeline"
            )
        )

    def test_what_question_is_not_exact(self):
        self.assertFalse(
            _is_exact_or_document_query("What are the main security risks?")
        )

    def test_why_question_is_not_exact(self):
        self.assertFalse(
            _is_exact_or_document_query("Why does the system use reranking?")
        )


if __name__ == "__main__":
    unittest.main()
