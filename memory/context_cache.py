"""
Per-session context cache.

Stores the most recent retrieved context so follow-up questions can
reference what was previously retrieved without re-running the pipeline.

Two context types share the same key (only one active at a time):
  - faq:          retrieved docs + answer from last FAQ query
  - troubleshooting: diagnostic context + root cause from agent

Redis key: chat:cache:{tenant_id}:{user_id}
TTL: 2 hours (see config/memory.yaml)
"""

import json
import logging
from typing import Optional

from memory.config import (
    FAQ_CONTEXT_TTL_SECONDS,
    TROUBLESHOOTING_CONTEXT_TTL_SECONDS as DIAGNOSTIC_CONTEXT_TTL_SECONDS,
    cache_key as _cache_key,
)

_logger = logging.getLogger("memory.context_cache")


# ── Save ──────────────────────────────────────────────────────────────────────

def save_faq_context(
    tenant_id: str,
    user_id: str,
    question: str,
    retrieved_docs: list[str],
    answer: str,
) -> None:
    """Store the last FAQ retrieved context and answer. TTL: 1 day."""
    _save(tenant_id, user_id, {
        "type": "faq",
        "question": question,
        "retrieved_docs": retrieved_docs,
        "answer": answer,
    }, ttl=FAQ_CONTEXT_TTL_SECONDS)


def save_diagnostic_context(
    tenant_id: str,
    user_id: str,
    employee_id: str,
    diagnostic_context: str,
    root_cause: str,
) -> None:
    """Store the last troubleshooting diagnostic context. TTL: 3 days."""
    _save(tenant_id, user_id, {
        "type": "troubleshooting",
        "employee_id": employee_id,
        "diagnostic_context": diagnostic_context,
        "root_cause": root_cause,
    }, ttl=DIAGNOSTIC_CONTEXT_TTL_SECONDS)


# ── Load ──────────────────────────────────────────────────────────────────────

def load_context(tenant_id: str, user_id: str) -> Optional[dict]:
    """
    Load the current session context.
    Returns None if nothing is cached or Redis is unavailable.
    """
    try:
        from memory.redis_client import get_redis_client
        raw = get_redis_client().get(_cache_key(tenant_id, user_id))
        return json.loads(raw) if raw else None
    except Exception as e:
        _logger.debug(f"[context_cache] load failed: {e}")
        return None


def load_diagnostic_context(tenant_id: str, user_id: str) -> Optional[str]:
    """Convenience: return just the diagnostic_context string if type=troubleshooting."""
    ctx = load_context(tenant_id, user_id)
    if ctx and ctx.get("type") == "troubleshooting":
        return ctx.get("diagnostic_context")
    return None


def load_faq_context(tenant_id: str, user_id: str) -> Optional[dict]:
    """Convenience: return faq context dict if type=faq."""
    ctx = load_context(tenant_id, user_id)
    if ctx and ctx.get("type") == "faq":
        return ctx
    return None


# ── Clear ─────────────────────────────────────────────────────────────────────

def clear_context(tenant_id: str, user_id: str) -> None:
    """Delete session context (goodbye or session end)."""
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().delete(_cache_key(tenant_id, user_id))
    except Exception as e:
        _logger.debug(f"[context_cache] clear failed: {e}")


# ── Internal ──────────────────────────────────────────────────────────────────

def _save(tenant_id: str, user_id: str, data: dict, ttl: int = DIAGNOSTIC_CONTEXT_TTL_SECONDS) -> None:
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().setex(
            _cache_key(tenant_id, user_id),
            ttl,
            json.dumps(data, ensure_ascii=False),
        )
    except Exception as e:
        _logger.debug(f"[context_cache] save failed: {e}")


