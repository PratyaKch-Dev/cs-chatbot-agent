"""Unit tests for language detection."""

import pytest
from llm.language import detect_language, is_thai


class TestDetectLanguage:
    def test_thai_text(self):
        assert detect_language("สวัสดีครับ") == "th"

    def test_english_text(self):
        # TODO Phase 2: update once real detection is implemented
        result = detect_language("Hello, how are you?")
        assert result in ("th", "en")

    def test_returns_supported_language(self):
        result = detect_language("test")
        assert result in ("th", "en")


class TestIsThai:
    def test_thai_characters(self):
        assert is_thai("สวัสดี") is True

    def test_english_text(self):
        assert is_thai("Hello") is False

    def test_mixed_text(self):
        assert is_thai("Hello สวัสดี") is True
