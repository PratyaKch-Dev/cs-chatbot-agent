"""
Context Resolver — conversation state interpretation, no LLM.

Two responsibilities:
  Memory Loader   — loads active_context, history, summary, pending_image from Redis
  Context Interpreter — detects FlowAction for early-exit cases only (END_FLOW,
    TRIGGER_HANDOFF). Everything else returns NEW so the LLM router can decide
    whether the message is a followup (is_new=False) or a genuinely new topic (is_new=True).

Output: ContextResolution dataclass consumed by the orchestrator.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

_logger = logging.getLogger("pipeline.context_resolver")

RESOLVER_VERSION = "v2"
MAX_CONFIRMATION_AGE_MINUTES = 30

_TZ_BKK = timezone(timedelta(hours=7))


# ── FlowAction ────────────────────────────────────────────────────────────────

class FlowAction(str, Enum):
    END_FLOW        = "end_flow"        # user satisfied or said goodbye
    TRIGGER_HANDOFF = "trigger_handoff" # user replied "no" to confirmation → run handoff
    CONTINUE_FLOW   = "continue_flow"   # same topic, short/ambiguous reply
    TOPIC_SHIFT     = "topic_shift"     # clearly different domain → close old flow
    NEW             = "new"             # no active context
    AMBIGUOUS       = "ambiguous"       # unclear → LLM fallback


# ── ContextResolution ─────────────────────────────────────────────────────────

@dataclass
class ContextResolution:
    flow_action:      FlowAction
    resolver_reason:  str         # e.g. "awaiting_confirmation_yes_word"
    resolver_version: str         # bump when logic changes ("v1", "v2", ...)
    enriched_query:   str         # for SetFit + retrieval
    active_intent:    str         # current flow label if continuing, else ""
    pending_image:    str         # loaded from Redis, passed downstream
    history:          list[dict]  = field(default_factory=list)
    summary:          str         = ""
    active_context:   dict        = field(default_factory=dict)


# ── Word lists ────────────────────────────────────────────────────────────────

_YES_WORDS = {
    "ได้แล้ว", "โอเค", "ok", "ขอบคุณ", "ขอบคุณมาก", "ขอบใจ",
    "ขอบคุณค่ะ", "ขอบคุณครับ", "เรียบร้อย", "แก้ได้แล้ว",
    "solved", "thank", "thanks", "resolved", "done",
    # removed "ได้เลย" — appears as substring in "ยังไม่ได้เลย" → false positive
}

_NO_WORDS = {
    "ยังไม่ได้", "ยังมีปัญหา", "ยังพบปัญหา", "ยังไม่ได้เลย", "ยังไม่แก้",
    "ยังคงเป็นอยู่", "ไม่ได้", "ยังเป็นอยู่", "ไม่หาย", "พบปัญหา",
    "still", "still not", "not working", "not resolved", "still have",
}

_END_WORDS = _YES_WORDS | {
    "ลาก่อน", "บาย", "bye", "goodbye", "แล้วกัน", "แล้วเจอกัน",
}

# Phrases the user types/clicks when they explicitly want a human agent.
# Triggers TRIGGER_HANDOFF immediately, bypassing the recheck loop.
_HANDOFF_REQUEST_WORDS = {
    "ต้องการโอน", "โอนไปให้เจ้าหน้าที่", "โอนไปเจ้าหน้าที่",
    "ติดต่อเจ้าหน้าที่", "คุยกับคน", "คุยกับเจ้าหน้าที่",
    "talk to agent", "talk to human", "transfer me", "speak with",
    "ต้องการแอดมิน",
}


# ── Enriched query builder ────────────────────────────────────────────────────

def _build_enriched_query(message: str) -> str:
    return message


# ── Memory Loader ─────────────────────────────────────────────────────────────

def _load_active_context(tenant_id: str, user_id: str) -> Optional[dict]:
    try:
        from memory.active_context import load
        return load(tenant_id, user_id)
    except Exception as e:
        _logger.warning(f"[resolver] active_context load failed: {e}")
        return None


def _load_history(tenant_id: str, user_id: str, language: str) -> list[dict]:
    try:
        from memory.history import load_history
        return load_history(tenant_id, user_id, language)
    except Exception as e:
        _logger.warning(f"[resolver] history load failed: {e}")
        return []


def _load_summary(tenant_id: str, user_id: str, language: str) -> str:
    try:
        from memory.summarizer import load_summary
        return load_summary(tenant_id, user_id, language) or ""
    except Exception as e:
        _logger.warning(f"[resolver] summary load failed: {e}")
        return ""


def _load_pending_image(tenant_id: str, user_id: str) -> str:
    try:
        from memory.pending_image import load_pending_image
        return load_pending_image(tenant_id, user_id) or ""
    except Exception as e:
        _logger.warning(f"[resolver] pending_image load failed: {e}")
        return ""


# ── Stale check ───────────────────────────────────────────────────────────────

def _confirmation_age_minutes(active_context: dict) -> float:
    updated_at = active_context.get("updated_at", "")
    if not updated_at:
        return float("inf")
    try:
        dt = datetime.fromisoformat(updated_at)
        now = datetime.now(_TZ_BKK)
        delta = now - dt
        return delta.total_seconds() / 60
    except Exception:
        return float("inf")


# ── Message classifiers ───────────────────────────────────────────────────────

# A pure resolution signal is short by nature ("ครับ", "ขอบคุณ", "ได้แล้วค่ะ").
# Anything longer almost always carries an additional question or context shift
# (e.g. "เข้ามาได้แล้ว ถอนเงินยังไงหรอ"). For longer messages we skip the
# keyword shortcut and let the LLM router classify the full intent.
_PURE_SIGNAL_MAX_CHARS = 20


def _is_pure_signal(message: str) -> bool:
    return len(message.strip()) <= _PURE_SIGNAL_MAX_CHARS


def _is_yes(message: str) -> bool:
    msg = message.strip().lower()
    if not _is_pure_signal(msg):
        return False
    return any(w in msg for w in _YES_WORDS)


def _is_no(message: str) -> bool:
    msg = message.strip().lower()
    if not _is_pure_signal(msg):
        return False
    return any(w in msg for w in _NO_WORDS)


def _is_end(message: str) -> bool:
    msg = message.strip().lower()
    if not _is_pure_signal(msg):
        return False
    return any(w in msg for w in _END_WORDS)


def _is_handoff_request(message: str) -> bool:
    """Detect explicit user request to be transferred to a support agent."""
    msg = message.strip().lower()
    return any(w in msg for w in _HANDOFF_REQUEST_WORDS)


# ── Context Interpreter ───────────────────────────────────────────────────────

def _interpret(
    message: str,
    active_context: Optional[dict],
) -> tuple[FlowAction, str, str]:
    """
    Returns (flow_action, resolver_reason, active_intent).

    Only handles early-exit cases deterministically:
      END_FLOW        — goodbye / resolved words
      TRIGGER_HANDOFF — "no" reply to awaiting_confirmation
      NEW             — everything else (LLM router decides is_new for followup detection)
    """
    if not active_context:
        if _is_end(message):
            return FlowAction.END_FLOW, "end_word_no_context", ""
        return FlowAction.NEW, "no_active_context", ""

    status        = active_context.get("status", "active")
    active_intent = active_context.get("intent", "")

    # Explicit user request to talk to an agent — fires regardless of status.
    if _is_handoff_request(message):
        return FlowAction.TRIGGER_HANDOFF, "user_requested_handoff", active_intent

    # ── awaiting_confirmation: resolver handles yes/no only ───────────────────
    if status == "awaiting_confirmation":
        age = _confirmation_age_minutes(active_context)
        if age > MAX_CONFIRMATION_AGE_MINUTES:
            _logger.info(f"[resolver] confirmation stale ({age:.0f} min) → NEW")
            return FlowAction.NEW, "awaiting_confirmation_expired_30min", ""

        if _is_yes(message):
            return FlowAction.END_FLOW, "awaiting_confirmation_yes_word", active_intent
        if _is_no(message):
            return FlowAction.TRIGGER_HANDOFF, "awaiting_confirmation_no_word", active_intent
        # Other reply → LLM router decides
        return FlowAction.NEW, "awaiting_confirmation_other", active_intent

    # ── Normal turn — goodbye words are the only deterministic early exit ─────
    if _is_end(message):
        return FlowAction.END_FLOW, "end_word_detected", active_intent

    # LLM router will set is_new=False when this is a followup, is_new=True for new topic
    return FlowAction.NEW, "active_context_let_llm_decide", ""


# ── Public API ────────────────────────────────────────────────────────────────

def resolve(
    tenant_id: str,
    user_id: str,
    message: str,
    language: str,
) -> ContextResolution:
    """
    Load all Redis state and interpret conversation flow action.
    Returns a ContextResolution — no LLM calls, no side effects.
    """
    active_context = _load_active_context(tenant_id, user_id)
    history        = _load_history(tenant_id, user_id, language)
    summary        = _load_summary(tenant_id, user_id, language)
    pending_image  = _load_pending_image(tenant_id, user_id)

    flow_action, reason, active_intent = _interpret(message, active_context)

    enriched_query = _build_enriched_query(message)

    _logger.info(
        f"[resolver] v={RESOLVER_VERSION} action={flow_action.value} "
        f"reason={reason} intent={active_intent!r} query={enriched_query!r}"
    )

    return ContextResolution(
        flow_action      = flow_action,
        resolver_reason  = reason,
        resolver_version = RESOLVER_VERSION,
        enriched_query   = enriched_query,
        active_intent    = active_intent,
        pending_image    = pending_image,
        history          = history,
        summary          = summary,
        active_context   = active_context or {},
    )
