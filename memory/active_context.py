"""
Active conversation context.

Tracks what the user is currently talking about — topic, remark, open case.
This is conversation STATE, not a performance cache.

Redis key: chat:context:{tenant_id}:{user_id}
TTL: 30 min for troubleshooting (follows session), 1 day for FAQ
     (see config/memory.yaml)

Shape — FAQ:
{
  "intent":         "faq",
  "topic":          "download_app",
  "remark":         "user clarified they use iOS",
  "last_user_need": "iOS app download link",
  "status":         "active",
  "updated_at":     "2026-04-20T10:30:00+07:00"
}

Shape — Troubleshooting:
{
  "intent":           "troubleshooting",
  "topic":            "withdrawal_issue",
  "sub_type":         "troubleshooting_withdrawal",   # agent API key — what to call on recheck
  "employee_id":      "12345",
  "remark":           "user asked to recheck after contacting HR",
  "last_root_cause":  "incomplete_attendance",
  "status":           "active",
  "updated_at":       "2026-04-20T10:35:00+07:00"
}

status values: active | resolved | stale
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from memory.config import (
    FAQ_CONTEXT_TTL_SECONDS,
    TROUBLESHOOTING_CONTEXT_TTL_SECONDS,
    context_key as _context_key,
)

_logger = logging.getLogger("memory.active_context")

_TZ_BKK = timezone(timedelta(hours=7))


# ── Save ──────────────────────────────────────────────────────────────────────

def save_faq_context(
    tenant_id: str,
    user_id: str,
    topic: str,
    remark: str,
    last_user_need: str = "",
    status: str = "active",
) -> None:
    """Save or overwrite active FAQ context."""
    _save(tenant_id, user_id, {
        "intent":         "faq",
        "topic":          topic,
        "remark":         remark,
        "last_user_need": last_user_need,
        "status":         status,
        "updated_at":     _now(),
    }, ttl=FAQ_CONTEXT_TTL_SECONDS)


def save_troubleshooting_context(
    tenant_id: str,
    user_id: str,
    topic: str,
    remark: str,
    employee_id: str = "",
    last_root_cause: str = "",
    sub_type: str = "",
    status: str = "active",
) -> None:
    """Save or overwrite active troubleshooting context."""
    _save(tenant_id, user_id, {
        "intent":          "troubleshooting",
        "topic":           topic,
        "sub_type":        sub_type,
        "employee_id":     employee_id,
        "remark":          remark,
        "last_root_cause": last_root_cause,
        "status":          status,
        "updated_at":      _now(),
    }, ttl=TROUBLESHOOTING_CONTEXT_TTL_SECONDS)


def update_remark(tenant_id: str, user_id: str, remark: str) -> None:
    """Patch remark on existing active context without overwriting other fields."""
    ctx = load(tenant_id, user_id)
    if ctx is None:
        return
    ctx["remark"] = remark
    ctx["updated_at"] = _now()
    ttl = (FAQ_CONTEXT_TTL_SECONDS
           if ctx.get("intent") == "faq"
           else TROUBLESHOOTING_CONTEXT_TTL_SECONDS)
    _save(tenant_id, user_id, ctx, ttl=ttl)


def set_status(tenant_id: str, user_id: str, status: str) -> None:
    """Update status field (active / resolved / stale)."""
    ctx = load(tenant_id, user_id)
    if ctx is None:
        return
    ctx["status"] = status
    ctx["updated_at"] = _now()
    ttl = (FAQ_CONTEXT_TTL_SECONDS
           if ctx.get("intent") == "faq"
           else TROUBLESHOOTING_CONTEXT_TTL_SECONDS)
    _save(tenant_id, user_id, ctx, ttl=ttl)


# ── Load ──────────────────────────────────────────────────────────────────────

def load(tenant_id: str, user_id: str) -> Optional[dict]:
    """Load active context. Returns None if missing or Redis unavailable."""
    try:
        from memory.redis_client import get_redis_client
        raw = get_redis_client().get(_context_key(tenant_id, user_id))
        return json.loads(raw) if raw else None
    except Exception as e:
        _logger.warning(f"[active_context] load failed: {e}")
        return None


def load_for_router(tenant_id: str, user_id: str) -> str:
    """
    Return a compact string representation for injection into the router prompt.
    Returns empty string if no active context exists.
    """
    ctx = load(tenant_id, user_id)
    if not ctx or ctx.get("status") == "stale":
        return ""

    intent = ctx.get("intent", "")
    topic = ctx.get("topic", "")
    remark = ctx.get("remark", "")
    status = ctx.get("status", "active")

    if intent == "faq":
        need = ctx.get("last_user_need", "")
        return f"[active: faq | topic={topic} | remark={remark} | need={need} | status={status}]"
    elif intent == "troubleshooting":
        root = ctx.get("last_root_cause", "")
        emp = ctx.get("employee_id", "")
        return f"[active: troubleshooting | topic={topic} | employee_id={emp} | remark={remark} | last_root_cause={root} | status={status}]"

    return ""


# ── Clear ─────────────────────────────────────────────────────────────────────

def clear(tenant_id: str, user_id: str) -> None:
    """Delete active context (session end or explicit clear)."""
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().delete(_context_key(tenant_id, user_id))
        _logger.info(f"[active_context] cleared for {tenant_id}/{user_id}")
    except Exception as e:
        _logger.warning(f"[active_context] clear failed: {e}")


# ── Internal ──────────────────────────────────────────────────────────────────

def _save(tenant_id: str, user_id: str, data: dict, ttl: int) -> None:
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().setex(
            _context_key(tenant_id, user_id),
            ttl,
            json.dumps(data, ensure_ascii=False),
        )
    except Exception as e:
        _logger.warning(f"[active_context] save failed: {e}")


def _now() -> str:
    return datetime.now(_TZ_BKK).isoformat(timespec="seconds")
