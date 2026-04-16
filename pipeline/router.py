"""
Request router — LLM decides everything.

One fast haiku call (~150ms, max_tokens=10) classifies the message into
a specific label, which maps directly to a route + template_key.

Labels:
  greeting / thanks / goodbye / frustrated / confused  →  CHITCHAT
  missing_info                                          →  MISSING_INFO
  troubleshooting_withdrawal                            →  TROUBLESHOOTING
  troubleshooting_attendance                            →  TROUBLESHOOTING
  troubleshooting_account                               →  TROUBLESHOOTING
  troubleshooting_deduction                             →  TROUBLESHOOTING
  faq                                                   →  FAQ

Fallback (LLM unavailable): use detect_intent result → same label map.
"""

import logging
import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger("pipeline.router")


class Route(str, Enum):
    FAQ            = "faq"
    TROUBLESHOOTING = "troubleshooting"
    DIRECT         = "direct"
    TEMPLATE       = "template"       # kept for backward compat
    CHITCHAT       = "chitchat"
    MISSING_INFO   = "missing_info"


@dataclass
class RouteDecision:
    route: Route
    reason: str
    confidence: float = 1.0
    template_key: str = ""
    existing_context: Optional[str] = None


# ── Label → Route map (single source of truth) ────────────────────────────────
_LABEL_TO_ROUTE: dict[str, Route] = {
    "greeting":                    Route.CHITCHAT,
    "thanks":                      Route.CHITCHAT,
    "goodbye":                     Route.CHITCHAT,
    "frustrated":                  Route.CHITCHAT,
    "confused":                    Route.CHITCHAT,
    "missing_info":                Route.MISSING_INFO,
    "troubleshooting_withdrawal":  Route.TROUBLESHOOTING,
    "troubleshooting_attendance":  Route.TROUBLESHOOTING,
    "troubleshooting_account":     Route.TROUBLESHOOTING,
    "troubleshooting_deduction":   Route.TROUBLESHOOTING,
    "faq":                         Route.FAQ,
}

# Intent → label (for fallback when LLM is unavailable)
_INTENT_TO_LABEL: dict[str, str] = {
    "greeting":   "greeting",
    "thanks":     "thanks",
    "goodbye":    "goodbye",
    "frustrated": "frustrated",
    "confused":   "confused",
    "unclear":    "missing_info",
    "question":   "faq",
}

# Kept for backward compat
CHITCHAT_INTENTS    = {"greeting", "thanks", "goodbye", "frustrated", "confused"}
MISSING_INFO_INTENTS = {"unclear"}
TEMPLATE_INTENTS    = CHITCHAT_INTENTS | MISSING_INFO_INTENTS


# ── LLM classifier ────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """\
You are a message classifier for Salary Hero's customer support chatbot.

Classify the user's message into EXACTLY ONE of these labels:

greeting                  — hello, สวัสดี, hi, or any opening message
thanks                    — ขอบคุณ, thank you, ok, got it, ดีๆ, โอเค, รับทราบ
goodbye                   — ลาก่อน, bye, see you
frustrated                — ห่วย, แย่มาก, angry, terrible
confused                  — งง, ไม่เข้าใจ, don't understand
missing_info              — too vague to understand (ช่วยด้วย, มีปัญหา, single "?")
troubleshooting_withdrawal — can't withdraw, balance = 0, เบิกไม่ได้, ยอด 0, ซิงค์
troubleshooting_attendance — user's OWN record is wrong/missing: เช็คอินแล้วแต่ไม่ขึ้น, ประวัติเข้างานหาย, ระบบไม่บันทึก
troubleshooting_account   — suspended, blacklisted, สถานะบัญชี, ระงับ
troubleshooting_deduction — salary deducted, หักเงิน, ค่าปรับ, OT
faq                       — general policy/procedure question about Salary Hero features, rules, or what-to-do steps

Rules:
- Reply with ONLY the label. No spaces. No punctuation. No explanation.
- When greeting + question together → classify by the QUESTION, not the greeting.
- When unsure between troubleshooting sub-types → use troubleshooting_withdrawal.
- "ลืม check in ต้องทำอะไร" / "ขาดงานโดนหักไหม" / "มาสายกี่นาทีถึงโดนหัก" → faq  (policy question, not personal record issue)
- troubleshooting_attendance is ONLY when the user says their record IS wrong, not asking what to do about forgetting."""


def _parse_label(raw: str) -> Optional[str]:
    """
    Robustly extract a valid label from the raw LLM output.
    Tries exact match first, then scans for any known label substring.
    """
    cleaned = raw.strip().lower()
    # Remove everything except word chars and underscores
    cleaned = re.sub(r"[^\w]", "", cleaned)

    # Exact match
    if cleaned in _LABEL_TO_ROUTE:
        return cleaned

    # Substring scan — longest match wins (e.g. "troubleshooting_withdrawal" > "faq")
    for label in sorted(_LABEL_TO_ROUTE, key=len, reverse=True):
        if label in cleaned:
            return label

    return None


def _llm_classify(message: str, language: str) -> Optional[RouteDecision]:
    """
    Call haiku to classify the message.
    Returns None on failure so the caller can use the intent-based fallback.
    """
    try:
        from llm.client import call_llm
        raw = call_llm(
            messages=[{"role": "user", "content": message}],
            system=_ROUTER_SYSTEM,
            max_tokens=10,
            language=language,
        )
        label = _parse_label(raw)
        if label is None:
            _logger.warning(f"[router] LLM unknown label raw={raw!r}, using fallback")
            return None

        route = _LABEL_TO_ROUTE[label]
        _logger.info(f"[router] LLM → {label}")
        return RouteDecision(route=route, reason="llm", confidence=0.95, template_key=label)

    except Exception as exc:
        _logger.warning(f"[router] LLM failed ({exc}), using fallback")
        return None


_TS_KEYWORDS = {
    "th": [
        "เบิกไม่ได้", "เบิกเงินไม่ได้", "ยอด 0", "ยอด0", "0 บาท", "0บาท",
        "แสดง 0", "แสดงผล 0", "ไม่มียอด", "ยอดไม่ขึ้น", "เงินไม่ขึ้น",
        "เบิกไม่ผ่าน", "ทำไมเบิกไม่ได้", "ยอดเบิก", "เป็น 0", "เป็น0",
        "หักเงิน", "เงินเดือน", "ขาดงาน", "ซิงค์", "ลงทะเบียน",
        "สถานะ", "บัญชีถูก", "ระงับ",
        "การเข้างาน", "เข้างาน", "เช็คอิน", "เช็คเอาท์",
        "ประวัติการเข้างาน", "ประวัติเข้างาน", "บันทึกเวลา", "ลืม punch",
        "สายกี่วัน", "ขาดกี่วัน", "มาสาย",
    ],
    "en": [
        "can't withdraw", "cannot withdraw", "zero balance", "balance 0",
        "withdrawal failed", "not eligible",
        "attendance", "check in", "check out", "punch in", "punch out",
        "attendance record", "attendance history", "missed punch",
        "deduction", "payroll", "sync", "not working",
    ],
}


def _intent_fallback(intent, message: str = "", language: str = "th") -> RouteDecision:
    """
    Intent/keyword-based fallback when LLM is unavailable.
    Uses intent.value directly (no str()) so str-enum comparison works.
    For 'question' intent, also checks troubleshooting keywords.
    """
    intent_val = intent.value if hasattr(intent, "value") else str(intent)

    # Chitchat / missing-info — intent detection is reliable here
    label = _INTENT_TO_LABEL.get(intent_val)
    if label and label != "faq":
        return RouteDecision(
            route=_LABEL_TO_ROUTE[label],
            reason=f"fallback:intent={intent_val}",
            confidence=0.85,
            template_key=label,
        )

    # For 'question' intent: check troubleshooting keywords before defaulting to FAQ
    if message:
        msg_lower = message.lower()
        lang_key  = "th" if language == "th" else "en"
        for kw in _TS_KEYWORDS.get(lang_key, []):
            if kw in msg_lower:
                return RouteDecision(
                    route=Route.TROUBLESHOOTING,
                    reason=f"fallback:keyword={kw}",
                    confidence=0.8,
                    template_key="troubleshooting_withdrawal",  # safest default
                )

    return RouteDecision(
        route=Route.FAQ,
        reason="fallback:default",
        confidence=0.7,
        template_key="faq",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def decide_route(
    intent,
    message: str,
    language: str,
    tenant_id: str,
) -> RouteDecision:
    """
    LLM classifies the message into a specific label → route + template_key.
    Falls back to intent-based routing if LLM is unavailable.
    """
    decision = _llm_classify(message, language)
    if decision:
        return decision
    return _intent_fallback(intent, message, language)
