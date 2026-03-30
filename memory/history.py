"""
Chat history management.

Stores and retrieves conversation turns per user per language.
History is kept for HISTORY_TTL_DAYS days.
Only the most recent MAX_HISTORY_TURNS are returned for context.

Redis key: chat:memory:{tenant_id}:{user_id}:{language}
"""

HISTORY_TTL_SECONDS = 7 * 24 * 60 * 60   # 7 days
MAX_HISTORY_TURNS = 20                    # turns to load before summarization check
SUMMARIZATION_THRESHOLD = 15             # summarize if more than this many turns


def load_history(
    tenant_id: str,
    user_id: str,
    language: str,
    limit: int = MAX_HISTORY_TURNS,
) -> list[dict]:
    """
    Load recent conversation turns.

    Each turn is: {"role": "user"|"assistant", "content": str, "timestamp": float}

    TODO Phase 3: implement using get_redis_client().
    """
    raise NotImplementedError("Phase 3")


def save_turn(
    tenant_id: str,
    user_id: str,
    language: str,
    user_message: str,
    assistant_reply: str,
) -> None:
    """
    Append a user+assistant turn to history.

    TODO Phase 3: implement — push to Redis list, reset TTL.
    """
    raise NotImplementedError("Phase 3")


def is_history_too_long(history: list[dict]) -> bool:
    """Return True if history exceeds summarization threshold."""
    return len(history) > SUMMARIZATION_THRESHOLD


def _history_key(tenant_id: str, user_id: str, language: str) -> str:
    return f"chat:memory:{tenant_id}:{user_id}:{language}"
