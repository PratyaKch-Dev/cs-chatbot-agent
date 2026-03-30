"""
Redis client singleton.

Provides a single shared Redis connection for the entire application.
All memory modules (session, history, summarizer) use this.
"""

import os
from typing import Optional

# TODO Phase 1: implement
# import redis

_client = None   # Redis | None


def get_redis_client():
    """
    Return the Redis client singleton.
    Creates the connection on first call.

    TODO Phase 1: implement with connection pooling and health check.
    """
    raise NotImplementedError("Phase 1")


def check_redis_health() -> bool:
    """Ping Redis and return True if healthy.

    TODO Phase 1: implement.
    """
    raise NotImplementedError("Phase 1")
