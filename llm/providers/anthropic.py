"""
Anthropic Claude provider.

Default LLM provider. Uses claude-3-haiku for fast, cost-efficient responses.
Switch model via LLM_MODEL env var.

Phase 1 implementation.
"""

import os
from typing import Optional

from llm.providers.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "claude-3-haiku-20240307"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30


class AnthropicProvider(BaseLLMProvider):

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Call Claude via Anthropic SDK with retry on rate limits.

        TODO Phase 1: implement using anthropic SDK + tenacity retry.
        """
        raise NotImplementedError("Phase 1")

    def get_langchain_llm(self):
        """
        Return a LangChain ChatAnthropic instance.

        TODO Phase 1: implement.
        Example:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=self.model, api_key=self.api_key)
        """
        raise NotImplementedError("Phase 1")

    def get_model_name(self) -> str:
        return self.model
