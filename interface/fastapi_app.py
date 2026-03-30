"""
FastAPI application — LINE Messaging API webhook.

Handles:
- LINE webhook signature validation (HMAC-SHA256)
- Message routing to pipeline orchestrator
- Health check endpoint
"""

import hashlib
import hmac
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# TODO Phase 1: import orchestrator
# from pipeline.orchestrator import handle_message

app = FastAPI(title="CS Chatbot Agent", version="0.1.0")

_channel_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
_channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

configuration = Configuration(access_token=_channel_access_token)
parser = WebhookParser(_channel_secret)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """Receive LINE webhook events, validate signature, dispatch to orchestrator."""
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    # Validate HMAC-SHA256 signature
    # TODO Phase 1: move to middleware
    expected = hmac.new(
        _channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    import base64
    if not hmac.compare_digest(base64.b64encode(expected).decode(), signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to parse webhook")

    async with AsyncApiClient(configuration) as api_client:
        line_bot_api = AsyncMessagingApi(api_client)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue
            if not isinstance(event.message, TextMessageContent):
                continue

            user_id = event.source.user_id
            tenant_id = _resolve_tenant(event)
            user_message = event.message.text

            # TODO Phase 3: call orchestrator
            # reply_text = await handle_message(
            #     tenant_id=tenant_id,
            #     user_id=user_id,
            #     message=user_message,
            # )
            reply_text = "ระบบกำลังพัฒนาอยู่ / System under development"

            await line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)],
                )
            )

    return Response(content="OK", status_code=200)


def _resolve_tenant(event: Any) -> str:
    """Resolve tenant ID from LINE event (channel / group context).

    TODO Phase 8: implement real tenant resolution from tenants.yaml
    """
    return "hns"
