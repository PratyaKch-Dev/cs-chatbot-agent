"""
Session management.

A session groups messages from one continuous conversation window.
Sessions expire after SESSION_TTL_SECONDS of inactivity.

Redis key: chat:session:{tenant_id}:{user_id}
"""

import json
import time
from typing import Optional

SESSION_TTL_SECONDS = 30 * 60   # 30 minutes


def get_or_create_session(tenant_id: str, user_id: str) -> dict:
    """
    Return existing active session or create a new one.

    Session dict contains:
        - session_id: str
        - tenant_id: str
        - user_id: str
        - created_at: float (unix timestamp)
        - last_active: float

    TODO Phase 3: implement using get_redis_client().
    """
    raise NotImplementedError("Phase 3")


def touch_session(tenant_id: str, user_id: str) -> None:
    """Update last_active and reset TTL.

    TODO Phase 3: implement.
    """
    raise NotImplementedError("Phase 3")


def end_session(tenant_id: str, user_id: str) -> None:
    """Explicitly end a session (e.g., on goodbye intent).

    TODO Phase 3: implement.
    """
    raise NotImplementedError("Phase 3")


def _session_key(tenant_id: str, user_id: str) -> str:
    return f"chat:session:{tenant_id}:{user_id}"
