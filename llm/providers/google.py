"""
Google Gemini provider.

Swap to Gemini via:
    LLM_PROVIDER=google
    LLM_MODEL=gemini-1.5-flash   (default)

Phase 8 implementation.
"""

import os
from typing import Optional

from llm.providers.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "gemini-1.5-flash"


class GoogleProvider(BaseLLMProvider):

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        TODO Phase 8: implement using google-generativeai SDK.
        Example:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(...)
        """
        raise NotImplementedError("Phase 8 — set LLM_PROVIDER=anthropic for now")

    def get_langchain_llm(self):
        """
        TODO Phase 8: implement.
        Example:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=self.model, google_api_key=self.api_key)
        """
        raise NotImplementedError("Phase 8 — set LLM_PROVIDER=anthropic for now")

    def get_model_name(self) -> str:
        return self.model
