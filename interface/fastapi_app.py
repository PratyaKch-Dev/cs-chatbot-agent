"""
FastAPI application — LINE Messaging API webhook.

Handles:
- LINE webhook signature validation (HMAC-SHA256)
- Multi-message debounce combining (memory.buffer)
- Message routing to pipeline orchestrator
- Reply via LINE Push API (so reply_token expiry doesn't affect combined messages)
- Health check endpoint
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from interface.freshchat_app import router as freshchat_router
from memory.buffer import append as buffer_append
from pipeline.orchestrator import handle_message

_logger = logging.getLogger("fastapi_app")

app = FastAPI(title="CS Chatbot Agent", version="0.1.0")
app.include_router(freshchat_router)

_channel_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
_channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

configuration = Configuration(access_token=_channel_access_token)
parser = WebhookParser(_channel_secret)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """Receive LINE webhook events, validate signature, buffer and dispatch."""
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    expected = base64.b64encode(
        hmac.new(_channel_secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to parse webhook")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue

        user_id = event.source.user_id
        tenant_id = _resolve_tenant(event)
        message = event.message.text

        buffer_key = f"{tenant_id}:{user_id}"
        await buffer_append(
            key=buffer_key,
            message=message,
            on_flush=_make_flush_handler(tenant_id, user_id),
        )

    # Return 200 immediately — LINE requires a fast ACK.
    # Actual reply is sent async by buffer after debounce window.
    return Response(content="OK", status_code=200)


def _make_flush_handler(tenant_id: str, user_id: str):
    """Return an async handler that processes the buffered batch and pushes the reply."""
    async def on_flush(messages: list[str]) -> None:
        combined = "\n".join(messages)
        _logger.info(f"[webhook] {tenant_id}/{user_id} processing {len(messages)} msg(s)")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: handle_message(
                tenant_id=tenant_id,
                user_id=user_id,
                message=combined,
                employee_id=user_id,
            ),
        )

        reply_text = result.answer
        if result.image_urls and not result.was_escalated:
            reply_text += "\n\n" + "\n".join(result.image_urls)

        async with AsyncApiClient(configuration) as api_client:
            await AsyncMessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=reply_text)],
                )
            )
        _logger.info(f"[webhook] {tenant_id}/{user_id} reply sent")

    return on_flush


def _resolve_tenant(event: Any) -> str:
    """Resolve tenant ID from LINE event. TODO Phase 8: map from tenants.yaml."""
    return "hns"
