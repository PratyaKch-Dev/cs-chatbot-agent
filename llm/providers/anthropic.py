"""
Anthropic Claude provider.

Default LLM provider. Uses claude-3-haiku for fast, cost-efficient responses.
Switch model via LLM_MODEL env var.

Phase 1 implementation.
"""

import logging
import os
from typing import Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from llm.providers.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "claude-3-haiku-20240307"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30


class AnthropicProvider(BaseLLMProvider):

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = anthropic.Anthropic(api_key=self.api_key)

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(anthropic.RateLimitError),
    )
    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Call Claude via Anthropic SDK with retry on rate limits."""
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        text = response.content[0].text.strip()
        logging.info(f"[LLM] tokens in={response.usage.input_tokens} out={response.usage.output_tokens}")

        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
        )

    def get_langchain_llm(self):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=self.model, api_key=self.api_key)

    def get_model_name(self) -> str:
        return self.model
