"""
Request router — LLM fallback for ambiguous messages only.

Context Resolver handles conversation state (no LLM).
LLM is called only for NEW / AMBIGUOUS / TOPIC_SHIFT cases.
search_query no longer generated here — lazy rewrite in _run_faq when score < 0.35.

Labels:
  chitchat_greeting | chitchat_thanks | chitchat_goodbye  →  CHITCHAT
  chitchat_frustrated | chitchat_confused                  →  CHITCHAT
  missing_info                                             →  MISSING_INFO
  troubleshooting_withdrawal                               →  TROUBLESHOOTING (live API)
  troubleshooting_signup                                   →  FAQ (label kept for analytics)
  troubleshooting_cant_find_company                        →  FAQ (label kept for analytics)
  troubleshooting_money_not_arrived                        →  FAQ (label kept for analytics)
  troubleshooting_cant_receive_otp                         →  FAQ (label kept for analytics)
  faq                                                      →  FAQ

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
    conv_state: str = "new_query"           # kept for compat
    followup_type: Optional[str] = None     # kept for compat
    search_query: str = ""
    is_new: bool = True                     # False = LLM says this is a followup on active context


# ── Label → Route map (single source of truth) ────────────────────────────────
_LABEL_TO_ROUTE: dict[str, Route] = {
    # new chitchat_* labels from _LLM_FALLBACK_SYSTEM
    "chitchat_greeting":   Route.CHITCHAT,
    "chitchat_thanks":     Route.CHITCHAT,
    "chitchat_goodbye":    Route.CHITCHAT,
    "chitchat_frustrated": Route.CHITCHAT,
    "chitchat_confused":   Route.CHITCHAT,
    # plain labels kept for keyword fallback backward compat
    "greeting":            Route.CHITCHAT,
    "thanks":              Route.CHITCHAT,
    "goodbye":             Route.CHITCHAT,
    "frustrated":          Route.CHITCHAT,
    "confused":            Route.CHITCHAT,
    "missing_info":                      Route.MISSING_INFO,
    # Only `withdrawal` actually needs live API data (balance/eligibility/sync).
    # Others route to FAQ — answers exist in the FAQ catalog (signup steps,
    # company search, money-not-arrived guidance, OTP 3-step troubleshooting).
    # The label is preserved as template_key for analytics in the trace.
    "troubleshooting_withdrawal":        Route.TROUBLESHOOTING,
    "troubleshooting_signup":            Route.FAQ,
    "troubleshooting_cant_find_company": Route.FAQ,
    "troubleshooting_money_not_arrived": Route.FAQ,
    "troubleshooting_cant_receive_otp":  Route.FAQ,
    "faq":                               Route.FAQ,
    # Explicit user request to talk to a human / be transferred. Classified by
    # the LLM router from any wording ("โอน", "คุยกับคน", "talk to agent",
    # "ขอเจ้าหน้าที่", anything semantically equivalent) — no keyword list to
    # maintain. Orchestrator catches this template_key and fires handoff.
    "handoff_request":                   Route.TROUBLESHOOTING,
}

# Strip chitchat_ prefix to get the template_key used by generate_answer
_TEMPLATE_KEY_MAP: dict[str, str] = {
    "chitchat_greeting":   "greeting",
    "chitchat_thanks":     "thanks",
    "chitchat_goodbye":    "goodbye",
    "chitchat_frustrated": "frustrated",
    "chitchat_confused":   "confused",
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

_LLM_FALLBACK_SYSTEM = """\
Salary Hero chatbot router. Classify the user's current message and decide if it is a new topic.

Context provided (HIGH PRIORITY — use this to judge is_new):
  - Recent history: last 4 turns of conversation
  - Active context: current open topic if any
  - Current message: the user's latest message

Labels:
  chitchat_greeting | chitchat_thanks | chitchat_goodbye
  chitchat_frustrated | chitchat_confused
  faq
  troubleshooting_withdrawal | troubleshooting_signup
  troubleshooting_cant_find_company | troubleshooting_money_not_arrived
  troubleshooting_cant_receive_otp
  handoff_request
  missing_info

Intent rules:
  handoff_request
    = user is explicitly asking to talk to a human agent / be transferred away
    from the bot. Wording varies — e.g. "โอน", "โอนให้เจ้าหน้าที่", "ขอแอดมิน",
    "คุยกับคน", "talk to agent", "transfer me", "ขอติดต่อเจ้าหน้าที่". Includes
    any clearly equivalent paraphrase. is_new=true always.
    Do NOT classify as handoff_request when the user is asking about a money
    transfer feature ("โอนเงินไปบัญชีไหน", "วิธีโอนเงิน") — that is `faq`.
  troubleshooting_withdrawal
    = user needs LIVE account/transaction lookup (balance 0, sync issue, not eligible).
    This is the only label that triggers an API call.
  troubleshooting_signup / cant_find_company / money_not_arrived / cant_receive_otp
    = user has a specific problem — but the answer lives in the FAQ catalog
    (registration steps, company search, money-not-arrived, OTP 3-step guidance).
    Classify with these labels for analytics; the orchestrator routes them through
    the FAQ pipeline instead of calling APIs.
  faq = generic knowledge / how-to / conditions / errors — everything else
  missing_info = message too vague to classify (preamble-only with NO question, single word, no topic)
  preamble-only (สอบถามหน่อย / ขอถามหน่อย / อยากสอบถาม with NO question after) → missing_info, is_new=true

  IMPORTANT — awaiting_confirmation continuation rule:
    When active context status = "awaiting_confirmation" AND the user replies with
    a short ambiguous message that doesn't itself introduce a new topic (examples:
    "เจออยู่", "ก็ยังนะ", "เหมือนเดิม", "ยังเลย", "ไม่ได้อยู่ดี", "เป็นเหมือนเดิม"),
    classify it as a CONTINUATION of the active sub_type with is_new=false.
    DO NOT classify these as missing_info — the active context provides the topic.
  greeting+question OR preamble+question → classify by the question content
  how-to questions (ยังไง / อย่างไร / วิธี / ขั้นตอน / how to) → faq, is_new=true always
  unsure troubleshooting subtype → troubleshooting_withdrawal

is_new rules:
  is_new=false: message is clearly a continuation of the SAME active topic
    (e.g. short reply about the same issue: "ยังไม่ได้", "ลองอีกที", "แล้วยังไง", "ตรวจอีกทีได้มั้ย")
  is_new=true: message introduces a different subject, corrects the bot's topic, or starts fresh
    - Correction markers: ไม่ใช่ / ฉันหมายถึง / ผมหมายถึง / ไม่ได้ถาม / not that / i mean
    - How-to questions (always fresh regardless of active context)
    - Chitchat intents (greeting, thanks, goodbye) are always is_new=true
    - No active context → always is_new=true
    - Preamble-only starters → always is_new=true
  When in doubt: trust the current message topic vs active context topic

Respond with raw JSON only — no markdown, no code fences, no explanation.
Output format: {"intent":"<label>","reason":"<short reason>","is_new":true|false}"""


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
    for key in ("intent", "reason"):
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
        if m:
            result[key] = m.group(1)
    m = re.search(r'"is_new"\s*:\s*(true|false)', text, re.IGNORECASE)
    if m:
        result["is_new"] = m.group(1).lower() == "true"

    return result if "intent" in result else None


def _llm_classify(
    message: str,
    language: str,
    recent_history: list[dict] | None = None,
    active_context: str = "",
    summary: str = "",
    image_situation: str = "",
) -> Optional[RouteDecision]:
    """
    Call fast LLM to classify message intent.
    Returns None on failure so the caller uses the intent-based fallback.
    conv_state / followup_type / search_query are no longer generated here —
    the Context Resolver handles conversation state, and search_query is
    rewritten lazily in _run_faq when the retrieval score is < 0.35.
    """
    try:
        from llm.client import call_llm

        parts: list[str] = []

        if summary:
            parts.append(f"Summary:\n{summary}")

        if recent_history:
            recent = recent_history[-4:]
            lines = []
            for m in recent:
                role = "User" if m["role"] == "user" else "Bot"
                lines.append(f"{role}: {m['content'][:120]}")
            parts.append("Recent history:\n" + "\n".join(lines))

        if active_context:
            parts.append(f"Active context:\n{active_context}")

        if image_situation:
            parts.append(
                f"User's screen (from image they sent earlier):\n{image_situation}\n"
                f"Use this as the user's current situation when classifying."
            )

        parts.append(f"Message: {message}")
        content = "\n\n".join(parts)

        raw = call_llm(
            messages=[{"role": "user", "content": content}],
            system=_LLM_FALLBACK_SYSTEM,
            max_tokens=1024,  # Gemini 2.5 Flash thinking can reach ~700-900 tokens with
                              # context+history+summary+image_situation; +JSON ~50 tokens.
                              # 512 was being exhausted by thinking → JSON truncated to 7 chars.
            language=language,
            step="router",
            json_mode=True,
        )

        parsed = _parse_router_json(raw)
        if not parsed:
            _logger.warning(f"[router] JSON parse failed raw={raw!r}, using fallback")
            return None

        intent = parsed.get("intent", "").strip()
        label  = _parse_label(intent) or _parse_label(raw)
        if label is None:
            _logger.warning(f"[router] unknown intent={intent!r}, using fallback")
            return None

        reason       = parsed.get("reason", "llm")
        route        = _LABEL_TO_ROUTE[label]
        template_key = _TEMPLATE_KEY_MAP.get(label, label)  # strip chitchat_ prefix
        # Chitchat intents are always new regardless of what LLM returns
        is_new = True if route == Route.CHITCHAT else bool(parsed.get("is_new", True))

        _logger.info(
            f"[router] LLM → intent={label} template_key={template_key} "
            f"is_new={is_new} reason={reason}"
        )

        return RouteDecision(
            route=route,
            reason=reason,
            confidence=0.9,
            template_key=template_key,
            conv_state="new_query",
            followup_type=None,
            search_query="",
            is_new=is_new,
        )

    except Exception as exc:
        _logger.warning(f"[router] LLM failed ({exc}), using fallback")
        return None


_TS_KEYWORDS = {
    "th": [
        "เบิกไม่ได้", "เบิกเงินไม่ได้", "ยอด 0", "ยอด0", "0 บาท", "0บาท",
        "แสดง 0", "แสดงผล 0", "ไม่มียอด", "ยอดไม่ขึ้น", "เงินไม่ขึ้น",
        "เบิกไม่ผ่าน", "ทำไมเบิกไม่ได้", "ยังเบิกไม่ได้", "ถึยังเบิก", "ถึคงเบิก",
        "ยอดเบิก", "เป็น 0", "เป็น0",
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
            is_new=True,
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
                    template_key="troubleshooting_withdrawal",
                    is_new=True,
                )

    return RouteDecision(
        route=Route.FAQ,
        reason="fallback:default",
        confidence=0.7,
        template_key="faq",
        is_new=True,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def _setfit_classify(message: str) -> Optional[RouteDecision]:
    """
    Try SetFit classifier first — no tokens, ~5ms.
    Returns None if model unavailable or confidence below threshold.
    """
    try:
        from pipeline.setfit_router import predict
        result = predict(message)
        if result is None:
            return None
        label, confidence = result
        label = _parse_label(label) or label
        if label not in _LABEL_TO_ROUTE:
            return None
        route        = _LABEL_TO_ROUTE[label]
        template_key = _TEMPLATE_KEY_MAP.get(label, label)
        _logger.info(f"[router] SetFit → label={label} conf={confidence:.3f}")
        return RouteDecision(
            route=route,
            reason=f"setfit:conf={confidence:.2f}",
            confidence=confidence,
            template_key=template_key,
            conv_state="new_query",
            is_new=True,  # SetFit used only when no active context
        )
    except Exception as exc:
        _logger.debug(f"[router] setfit_classify skipped: {exc}")
        return None


def decide_route(
    intent,
    message: str,
    language: str,
    tenant_id: str,
    recent_history: list[dict] | None = None,
    active_context: str = "",
    summary: str = "",
    image_situation: str = "",
) -> RouteDecision:
    """
    Route priority:
      1. SetFit  (no tokens, ~5ms) — if confidence >= threshold and no active context
      2. LLM                       — context-aware, returns is_new
      3. Intent keyword fallback   — if LLM unavailable
    """
    # 1. SetFit fast path — skip when active_context or image_situation is present
    setfit_skip: str = ""
    if active_context:
        setfit_skip = "setfit:skip(ctx)"
    elif image_situation:
        setfit_skip = "setfit:skip(img)"
    else:
        decision = _setfit_classify(message)
        if decision:
            return decision
        setfit_skip = "setfit:low_conf"

    # 2. LLM (context-aware)
    decision = _llm_classify(
        message, language,
        recent_history=recent_history,
        active_context=active_context,
        summary=summary,
        image_situation=image_situation,
    )
    if decision:
        decision.reason = f"{setfit_skip} → {decision.reason}"
        return decision

    # 3. Intent keyword fallback
    result = _intent_fallback(intent, message, language)
    result.reason = f"{setfit_skip} → {result.reason}"
    return result
