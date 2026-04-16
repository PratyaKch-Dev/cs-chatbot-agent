"""
LLM client factory.

Returns the configured provider based on LLM_PROVIDER env var.
All pipeline and agent code calls this — never import a provider directly.

Supported providers:
    anthropic  →  Claude (default)
    openai     →  GPT
    google     →  Gemini

Usage:
    from llm.client import get_provider, call_llm

    # Get LangChain LLM for chains/agents
    llm = get_provider().get_langchain_llm()

    # Direct one-shot call
    reply = call_llm(messages=[{"role": "user", "content": "Hello"}])
"""

import os
from functools import lru_cache
from typing import Optional

from llm.providers.base import BaseLLMProvider, LLMResponse

DEFAULT_MAX_TOKENS = 1024


@lru_cache(maxsize=1)
def get_provider() -> BaseLLMProvider:
    """
    Return the singleton LLM provider instance.
    Provider is determined by LLM_PROVIDER env var (default: anthropic).
    """
    provider_name = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider_name == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider()
    elif provider_name == "openai":
        from llm.providers.openai import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "google":
        from llm.providers.google import GoogleProvider
        return GoogleProvider()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider_name}'. "
            "Supported: anthropic, openai, google"
        )


def get_llm():
    """Return a LangChain-compatible chat model for use in chains and agents."""
    return get_provider().get_langchain_llm()


def call_llm(
    messages: list[dict],
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    language: str = "th",
) -> str:
    """
    One-shot LLM call. Returns reply text.
    Falls back to a safe message if provider raises.

    Args:
        messages: [{"role": "user"|"assistant", "content": str}, ...]
        system:   System prompt
        max_tokens: Max tokens to generate
        language: Used for fallback message language
    """
    try:
        response = get_provider().chat(messages, system=system, max_tokens=max_tokens)
        return response.text
    except NotImplementedError:
        raise
    except Exception as e:
        import logging
        logging.getLogger("llm.client").error(f"[LLM] API call failed: {type(e).__name__}: {e}")
        return get_provider().get_fallback_response(language)
