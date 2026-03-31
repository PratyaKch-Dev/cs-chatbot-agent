"""Unit tests for query text normalization."""

import pytest
from rag.query_cleaner import clean_query, _normalize_whitespace, _apply_synonyms


class TestNormalizeWhitespace:
    def test_collapses_spaces(self):
        assert _normalize_whitespace("hello   world") == "hello world"

    def test_strips_edges(self):
        assert _normalize_whitespace("  hello  ") == "hello"

    def test_newlines_collapsed(self):
        assert _normalize_whitespace("hello\n\nworld") == "hello world"


class TestApplySynonyms:
    def test_thai_synonym(self):
        assert _apply_synonyms("ถอนไม่ได้") == "ถอนเงินไม่ได้"

    def test_english_synonym(self):
        assert _apply_synonyms("cant withdraw") == "cannot withdraw"

    def test_no_match_unchanged(self):
        assert _apply_synonyms("hello world") == "hello world"


class TestCleanQuery:
    def test_lowercases(self):
        assert clean_query("Hello World") == "hello world"

    def test_strips_whitespace(self):
        assert clean_query("  hello  ") == "hello"

    def test_collapses_spaces(self):
        assert clean_query("hello   world") == "hello world"

    def test_punctuation_only_returns_empty(self):
        assert clean_query("???") == ""

    def test_empty_string(self):
        assert clean_query("") == ""

    def test_non_string_returns_empty(self):
        assert clean_query(None) == ""
        assert clean_query(123) == ""

    def test_applies_synonym(self):
        result = clean_query("cant withdraw")
        assert "cannot withdraw" in result

    def test_thai_text_preserved(self):
        result = clean_query("ถอนเงินได้กี่ครั้ง")
        assert "ถอนเงินได้กี่ครั้ง" in result

    def test_thai_synonym_applied(self):
        result = clean_query("ถอนไม่ได้")
        assert "ถอนเงินไม่ได้" in result
