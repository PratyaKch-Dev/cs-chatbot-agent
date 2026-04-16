"""
Google Gemini provider.

Swap to Gemini via:
    LLM_PROVIDER=google
    GOOGLE_API_KEY=your-key
    LLM_MODEL=gemini-2.5-flash   (default)
"""

import logging
import os
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from llm.providers.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3

_logger = logging.getLogger("llm.providers.google")


class GoogleProvider(BaseLLMProvider):

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set")

        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        self._genai = genai

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Call Gemini via google-generativeai SDK.

        Converts the OpenAI-style messages list into Gemini's format:
            {"role": "user"|"model", "parts": [str]}
        The system prompt is passed via system_instruction.
        """
        # Build Gemini history (all turns except the last user message)
        gemini_history = []
        for msg in messages[:-1]:
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        # Last message must be the user turn we're replying to
        last_msg = messages[-1]["content"] if messages else ""

        generation_config = {"max_output_tokens": max_tokens}

        model_kwargs: dict = {"generation_config": generation_config}
        if system:
            model_kwargs["system_instruction"] = system

        model = self._genai.GenerativeModel(self.model, **model_kwargs)
        chat_session = model.start_chat(history=gemini_history)
        response = chat_session.send_message(last_msg)

        text = response.text.strip()

        # Token counts (available on response.usage_metadata)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        _logger.info(
            f"[LLM] gemini tokens in={input_tokens} out={output_tokens}"
        )

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
        )

    def get_langchain_llm(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=self.model,
            google_api_key=self.api_key,
        )

    def get_model_name(self) -> str:
        return self.model
