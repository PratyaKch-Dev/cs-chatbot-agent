"""
Session management.

A session groups messages from one continuous conversation window.
Sessions expire after SESSION_TTL_SECONDS of inactivity (30 min).

Redis key: chat:session:{tenant_id}:{user_id}
"""

import json
import logging
import time
import uuid
from typing import Optional

from memory.config import SESSION_TTL_SECONDS, session_key as _session_key

_logger = logging.getLogger("memory.session")


def get_or_create_session(tenant_id: str, user_id: str) -> dict:
    """
    Return existing active session or create a new one.
    Always touches last_active and resets TTL.

    Returns session dict:
        session_id, tenant_id, user_id, created_at, last_active
    Falls back to a local dict if Redis unavailable.
    """
    try:
        from memory.redis_client import get_redis_client
        client = get_redis_client()
        key = _session_key(tenant_id, user_id)
        raw = client.get(key)

        if raw:
            session = json.loads(raw)
            session["last_active"] = time.time()
        else:
            session = {
                "session_id": str(uuid.uuid4()),
                "tenant_id":  tenant_id,
                "user_id":    user_id,
                "created_at": time.time(),
                "last_active": time.time(),
            }

        client.setex(key, SESSION_TTL_SECONDS, json.dumps(session))
        return session

    except Exception as e:
        _logger.warning(f"[session] get_or_create failed: {e}")
        return {
            "session_id": "local",
            "tenant_id":  tenant_id,
            "user_id":    user_id,
            "created_at": time.time(),
            "last_active": time.time(),
        }


def touch_session(tenant_id: str, user_id: str) -> None:
    """Update last_active and reset TTL on every message."""
    try:
        from memory.redis_client import get_redis_client
        client = get_redis_client()
        key = _session_key(tenant_id, user_id)
        raw = client.get(key)
        if raw:
            session = json.loads(raw)
            session["last_active"] = time.time()
            client.setex(key, SESSION_TTL_SECONDS, json.dumps(session))
    except Exception as e:
        _logger.warning(f"[session] touch failed: {e}")


def end_session(tenant_id: str, user_id: str) -> None:
    """Explicitly end a session (goodbye intent or manual clear)."""
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().delete(_session_key(tenant_id, user_id))
        _logger.info(f"[session] ended for {tenant_id}/{user_id}")
    except Exception as e:
        _logger.warning(f"[session] end failed: {e}")


