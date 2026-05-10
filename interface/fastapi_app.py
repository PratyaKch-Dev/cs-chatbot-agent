"""
FastAPI application — LINE Messaging API webhook + in-app chat API.

Handles:
- POST /chat        — in-app chat (mobile sends message + access_token directly)
- POST /webhook     — LINE Messaging API webhook (signature validation, debounce)
- GET  /health      — health check
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Configuration,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import FileMessageContent, ImageMessageContent, MessageEvent, StickerMessageContent, TextMessageContent

from interface.freshchat_app import router as freshchat_router
from llm.templates import FILE_NOT_SUPPORTED, IMAGE_CAPTION_PREFIX, THAI_TEMPLATES
from llm.intent import Intent
from llm.vision import describe_image
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


# ── In-app chat API ───────────────────────────────────────────────────────────

class _ChatRequest(BaseModel):
    user_id: str
    message: str
    access_token: str           # Salary Hero token; mock phase: pass employee_id (EMP001 etc.)
    tenant_id: str = "hns"


class _ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=_ChatResponse)
async def chat(body: _ChatRequest) -> _ChatResponse:
    """
    In-app chat endpoint — mobile sends message + access_token per request.

    The access_token is passed directly to the troubleshooting pipeline:
      - Mock phase (USE_MOCK_APIS=true): access_token = employee_id (e.g. "EMP001")
      - Real phase: access_token = Salary Hero Bearer token; BE derives user from it

    Response is synchronous — the mobile app waits for the reply.
    """
    if not body.user_id or not body.message:
        raise HTTPException(status_code=400, detail="user_id and message are required")

    _logger.info(f"[chat] {body.tenant_id}/{body.user_id} token={'set' if body.access_token else 'none'}")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: handle_message(
                tenant_id=body.tenant_id,
                user_id=body.user_id,
                message=body.message,
                access_token=body.access_token,
            ),
        )
        return _ChatResponse(reply=result.answer)
    except Exception as e:
        _logger.error(f"[chat] pipeline error for {body.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


# ── LINE webhook ──────────────────────────────────────────────────────────────

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

        user_id = event.source.user_id
        tenant_id = _resolve_tenant(event)

        if isinstance(event.message, StickerMessageContent):
            asyncio.create_task(_push_text(user_id, THAI_TEMPLATES[Intent.GREETING]))
            continue

        if isinstance(event.message, FileMessageContent):
            asyncio.create_task(_push_text(user_id, THAI_TEMPLATES[FILE_NOT_SUPPORTED]))
            continue

        if isinstance(event.message, ImageMessageContent):
            asyncio.create_task(_handle_image(tenant_id, user_id, event.message.id))
            continue

        if not isinstance(event.message, TextMessageContent):
            continue

        message = event.message.text
        buffer_key = f"{tenant_id}:{user_id}"
        await buffer_append(
            key=buffer_key,
            message=message,
            on_flush=_make_flush_handler(tenant_id, user_id),
        )

    # Return 200 immediately — LINE requires a fast ACK.
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


async def _push_text(user_id: str, text: str) -> None:
    async with AsyncApiClient(configuration) as api_client:
        await AsyncMessagingApi(api_client).push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


async def _handle_image(tenant_id: str, user_id: str, message_id: str) -> None:
    """Download LINE image, describe via vision, then buffer as text for the pipeline."""
    try:
        async with AsyncApiClient(configuration) as api_client:
            blob_api = AsyncMessagingApiBlob(api_client)
            content = await blob_api.get_message_content(message_id)
            image_bytes = content if isinstance(content, bytes) else await content.read()

        loop = asyncio.get_event_loop()
        description = await loop.run_in_executor(None, lambda: describe_image(image_bytes))
        message = IMAGE_CAPTION_PREFIX + description

        buffer_key = f"{tenant_id}:{user_id}"
        await buffer_append(
            key=buffer_key,
            message=message,
            on_flush=_make_flush_handler(tenant_id, user_id),
        )
    except Exception as exc:
        _logger.warning(f"[webhook] image handling failed for {user_id}: {exc}")
        await _push_text(user_id, THAI_TEMPLATES[FILE_NOT_SUPPORTED].replace("ไฟล์แนบ", "รูปภาพ"))


def _resolve_tenant(event: Any) -> str:
    """Resolve tenant ID from LINE event. TODO: map from tenants.yaml."""
    return "hns"
