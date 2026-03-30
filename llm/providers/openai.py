"""
OpenAI GPT provider.

Swap to GPT-4o or GPT-4o-mini via:
    LLM_PROVIDER=openai
    LLM_MODEL=gpt-4o-mini   (default)

Phase 8 implementation.
"""

import os
from typing import Optional

from llm.providers.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseLLMProvider):

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        TODO Phase 8: implement using openai SDK.
        Example:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *messages],
                max_tokens=max_tokens,
            )
        """
        raise NotImplementedError("Phase 8 — set LLM_PROVIDER=anthropic for now")

    def get_langchain_llm(self):
        """
        TODO Phase 8: implement.
        Example:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=self.model, api_key=self.api_key)
        """
        raise NotImplementedError("Phase 8 — set LLM_PROVIDER=anthropic for now")

    def get_model_name(self) -> str:
        return self.model
