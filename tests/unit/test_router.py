"""Unit tests for request router."""

import os
import pytest

# Disable LLM router so unit tests use keyword fallback (no API calls)
os.environ["LLM_ROUTER"] = "false"

from pipeline.router import decide_route, Route


class TestKeywordFallback:
    """Tests for keyword-based fallback routing (LLM_ROUTER=false)."""

    def test_greeting_routes_to_chitchat(self):
        d = decide_route("greeting", "สวัสดี", "th", "hns")
        assert d.route == Route.CHITCHAT

    def test_thanks_routes_to_chitchat(self):
        d = decide_route("thanks", "ขอบคุณ", "th", "hns")
        assert d.route == Route.CHITCHAT

    def test_goodbye_routes_to_chitchat(self):
        d = decide_route("goodbye", "bye", "en", "hns")
        assert d.route == Route.CHITCHAT

    def test_unclear_routes_to_missing_info(self):
        d = decide_route("unclear", "?", "th", "hns")
        assert d.route == Route.MISSING_INFO

    def test_question_routes_to_faq(self):
        d = decide_route("question", "วิธีเบิกเงินทำอย่างไร", "th", "hns")
        assert d.route == Route.FAQ

    def test_troubleshooting_keyword_th(self):
        d = decide_route("question", "เบิกไม่ได้เลยค่ะ", "th", "hns")
        assert d.route == Route.TROUBLESHOOTING

    def test_troubleshooting_keyword_en(self):
        d = decide_route("question", "I can't withdraw my balance", "en", "hns")
        assert d.route == Route.TROUBLESHOOTING

    def test_reason_contains_keyword_or_llm(self):
        d = decide_route("question", "เบิกไม่ได้", "th", "hns")
        assert any(k in d.reason for k in ("keyword", "llm", "fallback"))
