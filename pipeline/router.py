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

import json
import logging
import re
from enum import Enum
from dataclasses import dataclass, field
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
    conv_state: str = "new_query"           # new_query | followup | ambiguous
    followup_type: Optional[str] = None     # faq_followup | troubleshooting_recheck | None


# ── Label → Route map (single source of truth) ────────────────────────────────
_LABEL_TO_ROUTE: dict[str, Route] = {
    "greeting":                    Route.CHITCHAT,
    "thanks":                      Route.CHITCHAT,
    "goodbye":                     Route.CHITCHAT,
    "frustrated":                  Route.CHITCHAT,
    "confused":                    Route.CHITCHAT,
    "missing_info":                Route.MISSING_INFO,
    "troubleshooting_withdrawal":  Route.TROUBLESHOOTING,
    # Add new subtypes here when ready
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
Salary Hero chatbot router. Return JSON only.

intents: greeting|thanks|goodbye|frustrated|confused|missing_info|faq|troubleshooting_withdrawal

conv_state: new_query=new topic, followup=continues active context, ambiguous=unclear short msg
followup_type: faq_followup|troubleshooting_recheck|null (null unless conv_state=followup)
troubleshooting_recheck when: แจ้ง HR แล้ว / ช่วยเช็คอีกที / ตอนนี้ปกติหรือยัง / ยังไม่ได้
troubleshooting_attendance ONLY when user's OWN record is wrong (not policy questions)
greeting+question → classify by question. Unsure ts subtype → troubleshooting_withdrawal

{"intent":"<label>","conv_state":"new_query|followup|ambiguous","followup_type":"faq_followup|troubleshooting_recheck|null","confidence":0.0,"reason":"<short>"}"""


def _parse_label(raw: str) -> Optional[str]:
    """Extract a valid label from raw LLM output (used by fallback path)."""
    cleaned = re.sub(r"[^\w]", "", raw.strip().lower())
    if cleaned in _LABEL_TO_ROUTE:
        return cleaned
    for label in sorted(_LABEL_TO_ROUTE, key=len, reverse=True):
        if label in cleaned:
            return label
    return None


def _parse_router_json(raw: str) -> Optional[dict]:
    """
    Extract JSON from LLM output.
    Falls back to per-field regex extraction when JSON is truncated.
    """
    text = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Full parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Complete {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    # Per-field regex — handles truncated JSON
    result: dict = {}
    for key in ("intent", "conv_state", "followup_type", "reason"):
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
        if m:
            result[key] = m.group(1)
    m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    if m:
        result["confidence"] = float(m.group(1))
    if "followup_type" not in result and re.search(r'"followup_type"\s*:\s*null', text):
        result["followup_type"] = None

    return result if "intent" in result else None


def _llm_classify(
    message: str,
    language: str,
    recent_history: list[dict] | None = None,
    active_context: str = "",
    summary: str = "",
) -> Optional[RouteDecision]:
    """
    Call fast LLM to classify message + conv_state.
    Returns None on failure so the caller uses the intent-based fallback.
    """
    try:
        from llm.client import call_llm

        parts: list[str] = []

        if summary:
            parts.append(f"Summary:\n{summary[:200]}")

        if recent_history:
            recent = recent_history[-2:]  # last 1 exchange only — keeps input small
            lines = []
            for m in recent:
                role = "User" if m["role"] == "user" else "Bot"
                lines.append(f"{role}: {m['content'][:100]}")
            parts.append("Recent history:\n" + "\n".join(lines))

        if active_context:
            parts.append(f"Active context:\n{active_context}")

        parts.append(f"New message: {message}")
        content = "\n\n".join(parts)

        raw = call_llm(
            messages=[{"role": "user", "content": content}],
            system=_ROUTER_SYSTEM,
            max_tokens=250,
            language=language,
            step="router",
        )

        parsed = _parse_router_json(raw)
        if not parsed:
            _logger.warning(f"[router] JSON parse failed raw={raw!r}, using fallback")
            return None

        intent = parsed.get("intent", "").strip()
        label = _parse_label(intent) or _parse_label(raw)
        if label is None:
            _logger.warning(f"[router] unknown intent={intent!r}, using fallback")
            return None

        conv_state   = parsed.get("conv_state", "new_query")
        followup_type = parsed.get("followup_type") or None
        confidence   = float(parsed.get("confidence", 0.9))
        reason       = parsed.get("reason", "llm")

        route = _LABEL_TO_ROUTE[label]
        _logger.info(f"[router] LLM → intent={label} conv_state={conv_state} followup_type={followup_type} conf={confidence:.2f}")

        return RouteDecision(
            route=route,
            reason=reason,
            confidence=confidence,
            template_key=label,
            conv_state=conv_state,
            followup_type=followup_type if conv_state == "followup" else None,
        )

    except Exception as exc:
        _logger.warning(f"[router] LLM failed ({exc}), using fallback")
        return None


_TS_KEYWORDS = {
    "th": [
        "เบิกไม่ได้", "เบิกเงินไม่ได้", "ยอด 0", "ยอด0", "0 บาท", "0บาท",
        "แสดง 0", "แสดงผล 0", "ไม่มียอด", "ยอดไม่ขึ้น", "เงินไม่ขึ้น",
        "เบิกไม่ผ่าน", "ทำไมเบิกไม่ได้", "ยอดเบิก", "เป็น 0", "เป็น0",
    ],
    "en": [
        "can't withdraw", "cannot withdraw", "zero balance", "balance 0",
        "withdrawal failed", "not eligible",
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
    recent_history: list[dict] | None = None,
    active_context: str = "",
    summary: str = "",
) -> RouteDecision:
    """
    LLM classifies the message → route + conv_state + followup_type.
    Falls back to intent-based routing if LLM is unavailable.
    """
    decision = _llm_classify(
        message, language,
        recent_history=recent_history,
        active_context=active_context,
        summary=summary,
    )
    if decision:
        return decision
    return _intent_fallback(intent, message, language)
