"""
Human handoff context builder.

When the bot lacks confidence, it escalates to a live CS agent.
This module builds a warm handoff packet so the agent has full context:
    - Conversation summary
    - Issue description
    - Diagnostic data (from troubleshooting agent, if available)
    - Suggested next steps
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HandoffContext:
    tenant_id: str
    user_id: str
    issue_summary: str
    conversation_summary: str
    last_user_message: str
    grounding_score: float
    route_taken: str
    diagnostic_data: dict = field(default_factory=dict)
    suggested_next_steps: list[str] = field(default_factory=list)


def build_handoff_context(
    tenant_id: str,
    user_id: str,
    message: str,
    history: list[dict],
    grounding_score: float,
    route_taken: str,
    diagnostic_data: Optional[dict] = None,
) -> HandoffContext:
    """
    Build a structured handoff packet for the live CS agent.

    TODO Phase 3: implement conversation summarization + issue extraction.
    """
    raise NotImplementedError("Phase 3")


def format_handoff_message(context: HandoffContext, language: str) -> str:
    """
    Format the handoff context into a human-readable message
    to send to the CS agent's interface.

    TODO Phase 3: implement Thai + English formatting.
    """
    raise NotImplementedError("Phase 3")
