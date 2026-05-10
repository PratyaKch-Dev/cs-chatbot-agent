"""
Pending image context — stored when a user sends an image alone (no caption).

Flow:
  1. User sends image with no text → describe_image() → save_pending_image()
  2. Bot replies with a clarifying question
  3. On the user's next message, orchestrator.handle_message() calls
     load_pending_image() and prepends the description back into the query,
     then clear_pending_image().

Redis key: chat:pending_image:{tenant_id}:{user_id}
TTL: 30 min (config/memory.yaml — matches session window).
"""

import logging
from typing import Optional

from memory.config import PENDING_IMAGE_TTL_SECONDS, pending_image_key

_logger = logging.getLogger("memory.pending_image")


def save_pending_image(tenant_id: str, user_id: str, description: str) -> None:
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().setex(
            pending_image_key(tenant_id, user_id),
            PENDING_IMAGE_TTL_SECONDS,
            description,
        )
    except Exception as e:
        _logger.debug(f"[pending_image] save failed: {e}")


def load_pending_image(tenant_id: str, user_id: str) -> Optional[str]:
    try:
        from memory.redis_client import get_redis_client
        raw = get_redis_client().get(pending_image_key(tenant_id, user_id))
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return raw
    except Exception as e:
        _logger.debug(f"[pending_image] load failed: {e}")
        return None


def clear_pending_image(tenant_id: str, user_id: str) -> None:
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().delete(pending_image_key(tenant_id, user_id))
    except Exception as e:
        _logger.debug(f"[pending_image] clear failed: {e}")
