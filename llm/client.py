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
import time
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
    step: str = "answer",
) -> str:
    """
    One-shot LLM call. Returns reply text.
    Falls back to a safe message if provider raises.

    Args:
        messages:   [{"role": "user"|"assistant", "content": str}, ...]
        system:     System prompt
        max_tokens: Max tokens to generate
        language:   Used for fallback message language
        step:       Label recorded in the pipeline trace (e.g. "router", "answer")
    """
    try:
        t0 = time.perf_counter()
        response = get_provider().chat(messages, system=system, max_tokens=max_tokens)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Push to active pipeline trace (no-op when no trace is active)
        try:
            from utils.pipeline_logger import record_llm_call
            # history = all messages except the last one (prior exchanges)
            # prompt  = last message content (context + question for answer step)
            history_msgs = messages[:-1] if len(messages) > 1 else []
            last_user    = messages[-1]["content"] if messages else ""
            record_llm_call(
                step=step,
                model=response.model or get_provider().get_model_name(),
                in_tokens=response.input_tokens,
                out_tokens=response.output_tokens,
                latency_ms=latency_ms,
                system=system,
                history_msgs=history_msgs,
                prompt=last_user,
                reply=response.text,
            )
        except Exception:
            pass  # never let tracing break the call

        return response.text
    except NotImplementedError:
        raise
    except Exception as e:
        import logging
        logging.getLogger("llm.client").error(f"[LLM] API call failed: {type(e).__name__}: {e}")
        return get_provider().get_fallback_response(language)
