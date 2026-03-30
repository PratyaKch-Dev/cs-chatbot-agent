"""
LLM and agent call tracing.

Integrates with LangSmith (primary) or Langfuse (alternative)
to trace every LLM call, agent step, and tool invocation.

Provides:
- Request-level trace with tenant/user context
- Per-step latency and token counts
- Easy replay and debugging of failed requests
"""

import os
from typing import Optional

LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "cs-chatbot-agent")


def setup_tracing() -> None:
    """
    Initialize tracing on application startup.
    Configures LangSmith if API key is present, otherwise no-ops.

    TODO Phase 7: implement LangSmith setup.
    """
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return
    # TODO Phase 7: os.environ["LANGCHAIN_TRACING_V2"] = "true"
    #               os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT


def trace_request(
    tenant_id: str,
    user_id: str,
    route_taken: str,
    latency_ms: float,
    grounding_score: float,
    was_escalated: bool,
    token_count: Optional[int] = None,
) -> None:
    """
    Record a single request trace with key metadata.

    TODO Phase 7: implement — push to LangSmith run metadata.
    """
    pass  # no-op until Phase 7
