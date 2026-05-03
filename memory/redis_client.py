"""
Redis client singleton.

Provides a single shared Redis connection for the entire application.
All memory modules (session, history, summarizer, context_cache) use this.

Graceful degradation: if Redis is unavailable, callers catch the exception
and fall back to in-memory / empty state — the bot never crashes.
"""

import logging
import os

import redis

_client: redis.Redis | None = None
_available: bool | None = None  # None = untested, True = ok, False = down
_logger = logging.getLogger("memory.redis")


def get_redis_client() -> redis.Redis:
    """
    Return the Redis client singleton.
    Raises redis.RedisError if Redis is known to be unavailable (circuit open).
    """
    global _client, _available
    if _available is False:
        raise redis.RedisError("Redis unavailable (circuit open)")
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


def check_redis_health() -> bool:
    """Ping Redis, update circuit state, return True if healthy."""
    global _available
    try:
        get_redis_client().ping()
        if _available is not True:
            _logger.info("[Redis] connection OK")
        _available = True
        return True
    except Exception as e:
        if _available is not False:
            _logger.warning(f"[Redis] unavailable — memory features disabled: {e}")
        _available = False
        return False
