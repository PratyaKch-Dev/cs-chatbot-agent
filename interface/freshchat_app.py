"""
Freshchat webhook — stub.

TODO: implement when Freshchat integration is ready.

Flow to implement:
  1. Validate Freshchat webhook signature (X-Freshchat-Signature, HMAC-SHA256)
  2. Parse payload → tenant_id, user_id, message text and/or image attachment URL
  3. If image attachment is present:
       - Download image bytes via Freshchat API
       - description = llm.vision.describe_image(image_bytes)
       - buffer_append(key, IMAGE_CAPTION_PREFIX + description, on_flush=...)
     If text is present:
       - buffer_append(key, text, on_flush=...)
     (Both can arrive in the same webhook event — append both.)
  4. on_flush handler:
       img_only = pipeline.image_handler.extract_image_only_description(messages)
       if img_only:
           reply = pipeline.image_handler.build_clarifying_reply(
               tenant_id, user_id, img_only
           )
       else:
           result = pipeline.orchestrator.handle_message(
               tenant_id, user_id, "\\n".join(messages)
           )
           reply = result.answer
       freshchat.send_message(conversation_id, reply)
  5. Return 200 immediately (Freshchat requires fast acknowledgement)

Image-only flow (step 4 first branch) is what makes the bot ask a clarifying
question instead of guessing the user's intent. The orchestrator will pick up
the pending image context on the user's next reply (see pipeline/orchestrator.py).

Combining logic (debounce window): memory/buffer.py — same as the LINE webhook.
"""

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/freshchat", tags=["freshchat"])


@router.post("/webhook")
async def freshchat_webhook(request: Request) -> Response:
    """Receive Freshchat webhook events and queue messages for processing."""
    # TODO: validate signature
    # TODO: parse payload → tenant_id, user_id, text, image_url
    # TODO: if image_url → download → describe_image → buffer_append("[ภาพ] " + desc)
    # TODO: if text → buffer_append(text)
    # TODO: on_flush → image_handler.extract_image_only_description(messages)
    #         → either build_clarifying_reply OR handle_message
    #         → POST reply via Freshchat API
    return Response(content="OK", status_code=200)
