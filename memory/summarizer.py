"""
Rolling conversation summarizer — Phase 2 long-term memory.

After every exchange the summary is updated (not batched).
On the next session the summary is injected into the system prompt
so the bot knows what happened before without replaying raw messages.

Redis key: chat:summary:{tenant_id}:{user_id}:{language}
TTL: 7 days (reset on every update)

Update runs in a background thread — zero user-facing latency.
"""

import logging
import threading

from memory.config import SUMMARY_TTL_SECONDS, summary_key as _summary_key

_logger = logging.getLogger("memory.summarizer")

_SUMMARY_SYSTEM = {
    "th": (
        "คุณคือผู้สรุปบทสนทนาสั้นๆ\n"
        "อัปเดตสรุปบทสนทนาด้วยข้อความแลกเปลี่ยนใหม่\n"
        "สรุปให้กระชับใน 2-3 ประโยค ครอบคลุมปัญหาหลักและผลลัพธ์\n"
        "ตอบเป็นสรุปเท่านั้น ไม่ต้องมีคำนำหรือคำลงท้าย"
    ),
    "en": (
        "You are a concise conversation summarizer.\n"
        "Update the summary with the new exchange in 2-3 sentences.\n"
        "Cover the main issue and outcome only.\n"
        "Reply with the updated summary only — no preamble, no closing."
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────

def update_rolling_summary_async(
    tenant_id: str,
    user_id: str,
    language: str,
    user_message: str,
    assistant_reply: str,
) -> None:
    """
    Trigger a background thread to update the rolling summary.
    Returns immediately — caller is not blocked.
    """
    threading.Thread(
        target=_update_summary,
        args=(tenant_id, user_id, language, user_message, assistant_reply),
        daemon=True,
    ).start()


def load_summary(tenant_id: str, user_id: str, language: str) -> str:
    """Load the rolling summary. Returns empty string if none exists."""
    try:
        from memory.redis_client import get_redis_client
        value = get_redis_client().get(_summary_key(tenant_id, user_id, language))
        return value or ""
    except Exception as e:
        _logger.debug(f"[summarizer] load skipped: {e}")
        return ""


def clear_summary(tenant_id: str, user_id: str, language: str) -> None:
    """Delete summary on user request or goodbye."""
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().delete(_summary_key(tenant_id, user_id, language))
        _logger.info(f"[summarizer] cleared for {tenant_id}/{user_id}")
    except Exception as e:
        _logger.warning(f"[summarizer] clear failed: {e}")


# ── Internal ──────────────────────────────────────────────────────────────────

def _update_summary(
    tenant_id: str,
    user_id: str,
    language: str,
    user_message: str,
    assistant_reply: str,
) -> None:
    """Build updated summary via LLM and persist to Redis."""
    try:
        current = load_summary(tenant_id, user_id, language)
        lang = language if language in ("th", "en") else "th"

        if current:
            prompt = (
                f"Current summary:\n{current}\n\n"
                f"New exchange:\n"
                f"User: {user_message}\n"
                f"Bot: {assistant_reply}\n\n"
                "Update the summary to include this new exchange."
            )
        else:
            prompt = (
                f"Summarise this exchange in 2-3 sentences:\n"
                f"User: {user_message}\n"
                f"Bot: {assistant_reply}"
            )

        from llm.client import call_llm
        new_summary = call_llm(
            messages=[{"role": "user", "content": prompt}],
            system=_SUMMARY_SYSTEM[lang],
            max_tokens=300,
            language=lang,
            step="summarizer",
        )

        _save_summary(tenant_id, user_id, language, new_summary.strip())
        _logger.info(f"[summarizer] updated for {tenant_id}/{user_id}")

    except Exception as e:
        _logger.warning(f"[summarizer] update failed: {e}")


def _save_summary(tenant_id: str, user_id: str, language: str, summary: str) -> None:
    try:
        from memory.redis_client import get_redis_client
        get_redis_client().setex(
            _summary_key(tenant_id, user_id, language),
            SUMMARY_TTL_SECONDS,
            summary,
        )
    except Exception as e:
        _logger.debug(f"[summarizer] save skipped: {e}")


