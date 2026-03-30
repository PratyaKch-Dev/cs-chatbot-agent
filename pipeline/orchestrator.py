"""
Main pipeline orchestrator.

Coordinates the full request lifecycle:
    session → load history → detect language → detect intent
    → safety check → route → answer → save history
"""

from dataclasses import dataclass, field
from typing import Optional

# TODO Phase 3: wire all imports
# from memory.session import get_or_create_session
# from memory.history import load_history, save_turn
# from memory.summarizer import maybe_summarize
# from llm.language import detect_language
# from llm.intent import detect_intent
# from pipeline.safety import check_safety
# from pipeline.router import route
# from pipeline.answer_generator import generate_answer


@dataclass
class RequestContext:
    """All data assembled before routing."""
    tenant_id: str
    user_id: str
    message: str
    session_id: str = ""
    language: str = "th"
    intent: str = "question"
    history: list[dict] = field(default_factory=list)
    history_summary: str = ""
    is_safe: bool = True
    safety_reason: str = ""


@dataclass
class ResponseContext:
    """Final response with metadata."""
    reply: str
    route_taken: str = ""           # faq | troubleshooting | direct | template | handoff
    grounding_score: float = 1.0
    was_escalated: bool = False
    handoff_context: Optional[dict] = None


async def handle_message(
    tenant_id: str,
    user_id: str,
    message: str,
) -> str:
    """
    Full pipeline entry point.

    TODO Phase 3: implement fully.
    Returns the reply string to send back to the user.
    """
    raise NotImplementedError("Phase 3")
