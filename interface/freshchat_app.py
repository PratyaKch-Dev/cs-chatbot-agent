"""
Freshchat webhook — stub.

TODO: implement when Freshchat integration is ready.

Flow to implement:
  1. Validate Freshchat webhook signature (X-Freshchat-Signature header, HMAC-SHA256)
  2. Extract tenant_id, user_id, message text from payload
  3. Call memory.buffer.append(tenant_id, user_id, message) — Redis-backed queue
  4. Schedule a debounce task (e.g. 2s) that calls memory.buffer.flush() then pipeline
     - If another message arrives within the window, the timer resets (combining)
     - When timer fires: flush messages → join → handle_message → reply via Freshchat API
  5. Return 200 immediately (Freshchat requires fast acknowledgement)

Combining logic lives in memory/buffer.py (Redis + asyncio debounce).
Same concept as pipeline/combiner.py used by Gradio, but Redis-backed for multi-process.
"""

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/freshchat", tags=["freshchat"])


@router.post("/webhook")
async def freshchat_webhook(request: Request) -> Response:
    """Receive Freshchat webhook events and queue messages for processing."""
    # TODO: validate signature
    # TODO: parse payload → tenant_id, user_id, message
    # TODO: memory.buffer.append(tenant_id, user_id, message)
    # TODO: schedule debounce task (reset if already scheduled for this user)
    return Response(content="OK", status_code=200)
