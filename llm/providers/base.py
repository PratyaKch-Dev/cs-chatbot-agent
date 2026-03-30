"""
Abstract base class for all LLM providers.

Defines the common interface so any provider (Claude, GPT, Gemini, etc.)
can be swapped without changing any pipeline or agent code.

Switch provider via env var:  LLM_PROVIDER=anthropic | openai | google
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class BaseLLMProvider(ABC):

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Send a chat-style request and return the response.

        Args:
            messages: List of {"role": "user"|"assistant", "content": str}
            system:   System prompt (optional)
            max_tokens: Max tokens to generate

        Returns:
            LLMResponse with text + token counts
        """
        ...

    @abstractmethod
    def get_langchain_llm(self):
        """
        Return a LangChain-compatible chat model instance.
        Used by chains, agents, and memory components.

        Returns a BaseChatModel instance (e.g. ChatAnthropic, ChatOpenAI).
        """
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier string (e.g. 'claude-3-haiku-20240307')."""
        ...

    def get_fallback_response(self, language: str) -> str:
        """Graceful error message when provider is unavailable."""
        if language == "th":
            return "ขออภัย ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้งในอีกสักครู่"
        return "Sorry, the system is temporarily unavailable. Please try again in a moment."
