"""
Chat history management.

Stores the last MAX_EXCHANGES exchanges (user + assistant pairs) per user.
Each exchange = 2 messages, so MAX_EXCHANGES=3 → 6 messages stored.

Redis key: chat:memory:{tenant_id}:{user_id}:{language}
TTL: 7 days (reset on every save)
"""

import json
import logging
import time

from memory.config import HISTORY_TTL_SECONDS, MAX_EXCHANGES, history_key as _history_key

MAX_MESSAGES = MAX_EXCHANGES * 2

_logger = logging.getLogger("memory.history")


def load_history(
    tenant_id: str,
    user_id: str,
    language: str,
) -> list[dict]:
    """
    Load last MAX_EXCHANGES exchanges from Redis.
    Returns list of {"role": "user"|"assistant", "content": str}.
    Returns empty list if Redis unavailable.
    """
    try:
        from memory.redis_client import get_redis_client
        key = _history_key(tenant_id, user_id, language)
        items = get_redis_client().lrange(key, -MAX_MESSAGES, -1)
        history = []
        for item in items:
            entry = json.loads(item)
            history.append({"role": entry["role"], "content": entry["content"]})
        return history
    except Exception as e:
        _logger.warning(f"[history] load failed: {e}")
        return []


def save_turn(
    tenant_id: str,
    user_id: str,
    language: str,
    user_message: str,
    assistant_reply: str,
) -> None:
    """
    Append one exchange (user + assistant) to history.
    Trims to MAX_MESSAGES and resets TTL.
    """
    try:
        from memory.redis_client import get_redis_client
        client = get_redis_client()
        key = _history_key(tenant_id, user_id, language)
        now = time.time()
        client.rpush(key,
            json.dumps({"role": "user",      "content": user_message,    "ts": now}),
            json.dumps({"role": "assistant",  "content": assistant_reply, "ts": now}),
        )
        # Keep only the most recent MAX_MESSAGES
        client.ltrim(key, -MAX_MESSAGES, -1)
        client.expire(key, HISTORY_TTL_SECONDS)
    except Exception as e:
        _logger.warning(f"[history] save_turn failed: {e}")


def clear_history(tenant_id: str, user_id: str, language: str) -> None:
    """
    Delete all history for this user (called on goodbye or session end).
    """
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().delete(_history_key(tenant_id, user_id, language))
        _logger.info(f"[history] cleared for {tenant_id}/{user_id}")
    except Exception as e:
        _logger.warning(f"[history] clear failed: {e}")


