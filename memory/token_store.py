"""Redis store for access_token — keyed by LINE user_id.

TTL default: 24 hours. Mobile app re-registers on each session open.
Key pattern: auth:token:{user_id}
"""

import logging
from memory.redis_client import get_redis_client

_logger = logging.getLogger("memory.token_store")
_DEFAULT_TTL = 24 * 3600  # 24 hours


def save_token(user_id: str, access_token: str, ttl: int = _DEFAULT_TTL) -> None:
    key = f"auth:token:{user_id}"
    try:
        get_redis_client().set(key, access_token, ex=ttl)
    except Exception as e:
        _logger.warning(f"[token_store] save failed for {user_id}: {e}")


def load_token(user_id: str) -> str:
    key = f"auth:token:{user_id}"
    try:
        val = get_redis_client().get(key)
        return val or ""
    except Exception as e:
        _logger.warning(f"[token_store] load failed for {user_id}: {e}")
        return ""


def clear_token(user_id: str) -> None:
    key = f"auth:token:{user_id}"
    try:
        get_redis_client().delete(key)
    except Exception as e:
        _logger.warning(f"[token_store] clear failed for {user_id}: {e}")
