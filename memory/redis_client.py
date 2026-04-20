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
_logger = logging.getLogger("memory.redis")


def get_redis_client() -> redis.Redis:
    """
    Return the Redis client singleton.
    Creates the connection on first call using REDIS_URL env var.
    """
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _logger.info(f"[Redis] connected to {url}")
    return _client


def check_redis_health() -> bool:
    """Ping Redis and return True if healthy."""
    try:
        return get_redis_client().ping()
    except Exception as e:
        _logger.warning(f"[Redis] health check failed: {e}")
        return False
