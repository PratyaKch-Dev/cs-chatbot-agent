"""
Provider-agnostic image batch handler.

Inspect a flushed message batch (from buffer/combiner) and decide:
  - Image-only (no text alongside, no pre-combined question) → save the image
    description as pending context and reply with a clarifying question.
  - Anything else → caller runs the normal pipeline; the orchestrator will
    pick up the pending image (if any) and prepend it to the user's reply.

Used by both Gradio (testing UI) and Freshchat webhook (real target).
"""

import logging
from typing import Optional

from llm.templates import IMAGE_CAPTION_PREFIX, build_image_clarify_reply
from memory.pending_image import save_pending_image
from pipeline.image_intent import classify_image_intent
from utils.language import detect_language

_logger = logging.getLogger("image_flow")


def extract_image_only_description(messages: list[str]) -> Optional[str]:
    """
    Return the image description if the batch is image-only, else None.

    Image-only means: at least one message starts with IMAGE_CAPTION_PREFIX,
    no message is plain user text, and no image message is pre-combined with
    a question (e.g. "[ภาพ] desc\\nคำถาม: ...").
    """
    image_descs: list[str] = []
    has_text = False
    for m in messages or []:
        if not m or not m.strip():
            continue
        if m.startswith(IMAGE_CAPTION_PREFIX):
            # Pre-combined image+question — treat as a normal text turn.
            if "\nคำถาม:" in m or "\nQuestion:" in m:
                has_text = True
                continue
            image_descs.append(m[len(IMAGE_CAPTION_PREFIX):].strip())
        else:
            has_text = True
    if image_descs and not has_text:
        joined = "\n".join(image_descs)
        _logger.info(f"[image-flow] DETECTED image-only batch ({len(joined)} chars)")
        return joined
    return None


def build_clarifying_reply(tenant_id: str, user_id: str, description: str) -> str:
    """
    Save the pending image and return the clarifying-question text to send back.
    Caller is responsible for actually delivering the reply on its channel.
    """
    save_pending_image(tenant_id, user_id, description)
    language = detect_language(description) or "th"
    intent_id, suggestions = classify_image_intent(description, language)
    _logger.info(
        f"[image-flow] SAVED pending image for {tenant_id}/{user_id} "
        f"| intent={intent_id} | lang={language} | suggestions={len(suggestions)}"
    )
    return build_image_clarify_reply(language, description, suggestions)
