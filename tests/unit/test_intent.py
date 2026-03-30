"""Unit tests for intent detection."""

import pytest
from llm.intent import detect_intent, Intent


class TestDetectIntent:
    def test_greeting_thai(self):
        result = detect_intent("สวัสดีครับ", "th")
        assert result.intent == Intent.GREETING

    def test_greeting_english(self):
        result = detect_intent("Hello!", "en")
        assert result.intent == Intent.GREETING

    def test_thanks_thai(self):
        result = detect_intent("ขอบคุณมากครับ", "th")
        assert result.intent == Intent.THANKS

    def test_goodbye_thai(self):
        result = detect_intent("ลาก่อนนะ", "th")
        assert result.intent == Intent.GOODBYE

    def test_frustrated_thai(self):
        result = detect_intent("ห่วยมาก ใช้งานไม่ได้เลย", "th")
        assert result.intent == Intent.FRUSTRATED

    def test_question_falls_through(self):
        result = detect_intent("ถอนเงินได้กี่ครั้งต่อวัน", "th")
        assert result.intent == Intent.QUESTION
