"""
Multi-turn router test — mocked LLM.

Tests that router + active_context work together correctly across turns.
The LLM is mocked so tests are fast, deterministic, and need no API key.

Run:
    PYTHONPATH=. python scripts/test_multiturn_router.py
"""

import sys
import json
import unittest.mock as mock

# ── Fake Redis (no real Redis needed) ────────────────────────────────────────
try:
    import fakeredis
except ImportError:
    print("Install fakeredis first:  pip install fakeredis")
    sys.exit(1)

import memory.redis_client as _rc
_rc._client = fakeredis.FakeRedis(decode_responses=True)

from memory import active_context as ac
from pipeline.router import decide_route

TENANT = "hns"
USER   = "test_user_01"
LANG   = "th"

_PASS = 0
_FAIL = 0


def _fake_intent():
    class I:
        value = "question"
    return I()


def _turn(label: str, message: str, mock_json: dict,
          expected_conv_state: str, expected_followup_type=None):
    global _PASS, _FAIL
    ctx_str = ac.load_for_router(TENANT, USER)

    with mock.patch("llm.client.call_llm", return_value=json.dumps(mock_json)):
        decision = decide_route(
            intent=_fake_intent(),
            message=message,
            language=LANG,
            tenant_id=TENANT,
            active_context=ctx_str,
        )

    ok_state = decision.conv_state == expected_conv_state
    ok_ftype = decision.followup_type == expected_followup_type
    passed   = ok_state and ok_ftype
    icon     = "✅" if passed else "❌"
    if passed:
        _PASS += 1
    else:
        _FAIL += 1
    print(
        f"  {icon}  [{label}]\n"
        f"       msg={message!r}\n"
        f"       got    conv_state={decision.conv_state!r}  followup_type={decision.followup_type!r}  conf={decision.confidence:.2f}\n"
        f"       expect conv_state={expected_conv_state!r}  followup_type={expected_followup_type!r}\n"
    )
    return decision


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FLOW 1 — FAQ multi-turn (iOS clarification)")
print("=" * 60)

ac.clear(TENANT, USER)

_turn("T1 new query", "ดาวน์โหลดแอปได้ที่ไหน",
      {"intent": "faq", "conv_state": "new_query", "followup_type": None, "confidence": 0.95, "reason": "new faq question"},
      "new_query", None)
ac.save_faq_context(TENANT, USER, topic="download_app", remark="user asked where to download")

_turn("T2 iOS clarification", "ผมใช้ iOS ครับ",
      {"intent": "faq", "conv_state": "followup", "followup_type": "faq_followup", "confidence": 0.88, "reason": "platform clarification for active faq topic"},
      "followup", "faq_followup")
ac.update_remark(TENANT, USER, "user clarified they use iOS")

_turn("T3 acknowledgement", "โอเค ขอบคุณครับ",
      {"intent": "thanks", "conv_state": "followup", "followup_type": "faq_followup", "confidence": 0.82, "reason": "thanks but still in faq context"},
      "followup", "faq_followup")


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FLOW 2 — Troubleshooting recheck")
print("=" * 60)

ac.clear(TENANT, USER)

_turn("T1 new ts query", "ทำไมถอนเงินไม่ได้ครับ",
      {"intent": "troubleshooting_withdrawal", "conv_state": "new_query", "followup_type": None, "confidence": 0.97, "reason": "withdrawal issue, no prior context"},
      "new_query", None)
ac.save_troubleshooting_context(
    TENANT, USER,
    topic="withdrawal_issue", remark="user asked why withdrawal unavailable",
    employee_id="EMP003", last_root_cause="incomplete_attendance",
)

_turn("T2 recheck after HR", "แจ้ง HR แล้ว ช่วยเช็คอีกทีครับ",
      {"intent": "troubleshooting_withdrawal", "conv_state": "followup", "followup_type": "troubleshooting_recheck", "confidence": 0.93, "reason": "user contacted HR and requesting recheck"},
      "followup", "troubleshooting_recheck")
ac.update_remark(TENANT, USER, "user contacted HR and asked for recheck")

_turn("T3 status check", "ตอนนี้ปกติหรือยัง",
      {"intent": "troubleshooting_withdrawal", "conv_state": "followup", "followup_type": "troubleshooting_recheck", "confidence": 0.85, "reason": "asking for current status of open case"},
      "followup", "troubleshooting_recheck")


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FLOW 3 — Ambiguous continuation")
print("=" * 60)

# Active context still from flow 2
_turn("T1 ambiguous with ctx", "ตอนนี้ล่ะ",
      {"intent": "missing_info", "conv_state": "ambiguous", "followup_type": None, "confidence": 0.61, "reason": "short ambiguous message, active context exists"},
      "ambiguous", None)

ac.clear(TENANT, USER)
_turn("T2 ambiguous no ctx", "แล้วไงต่อ",
      {"intent": "missing_info", "conv_state": "ambiguous", "followup_type": None, "confidence": 0.55, "reason": "short ambiguous, no active context"},
      "ambiguous", None)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FLOW 4 — New query overrides active context")
print("=" * 60)

ac.save_faq_context(TENANT, USER, topic="download_app", remark="old topic still in Redis")

_turn("T1 brand new topic", "ลืมรหัสผ่านทำยังไง",
      {"intent": "faq", "conv_state": "new_query", "followup_type": None, "confidence": 0.94, "reason": "new faq unrelated to previous download_app context"},
      "new_query", None)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FLOW 5 — Low confidence ambiguous → should stay ambiguous (not force followup)")
print("=" * 60)

ac.save_troubleshooting_context(
    TENANT, USER,
    topic="withdrawal_issue", remark="previous case",
    employee_id="EMP001", last_root_cause="sync_pending",
)

_turn("T1 low conf ambiguous", "อันนี้ล่ะ",
      {"intent": "missing_info", "conv_state": "ambiguous", "followup_type": None, "confidence": 0.52, "reason": "too vague even with context present"},
      "ambiguous", None)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
total = _PASS + _FAIL
print(f"Total: {total}  |  Passed: {_PASS}  |  Failed: {_FAIL}  |  Accuracy: {_PASS/total*100:.0f}%")
print("=" * 60)
