"""
Conversation history summarizer.

When history exceeds the threshold, older turns are compressed into
a summary stored in Redis. Keeps context window manageable.

Redis key: chat:summary:{tenant_id}:{user_id}:{language}
"""

SUMMARY_TTL_SECONDS = 7 * 24 * 60 * 60   # 7 days


def maybe_summarize(
    tenant_id: str,
    user_id: str,
    language: str,
    history: list[dict],
) -> tuple[list[dict], str]:
    """
    If history is too long, summarize older turns via LLM.

    Returns:
        - recent_history: last N turns (kept as-is)
        - summary: compressed summary of older turns (or empty string)

    TODO Phase 4: implement using LLM summarization + Redis storage.
    """
    raise NotImplementedError("Phase 4")


def load_summary(tenant_id: str, user_id: str, language: str) -> str:
    """Load existing conversation summary from Redis.

    TODO Phase 4: implement.
    """
    raise NotImplementedError("Phase 4")


def save_summary(tenant_id: str, user_id: str, language: str, summary: str) -> None:
    """Persist a new conversation summary to Redis.

    TODO Phase 4: implement.
    """
    raise NotImplementedError("Phase 4")


def _summary_key(tenant_id: str, user_id: str, language: str) -> str:
    return f"chat:summary:{tenant_id}:{user_id}:{language}"
