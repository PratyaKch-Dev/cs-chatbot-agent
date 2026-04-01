"""
Request router.

Decides which pipeline path handles the request:
    - faq          → LangChain RAG retrieval
    - troubleshooting → LangChain ReAct agent with tools
    - direct       → Answer generation with existing context
    - template     → Pre-written template response (greeting, thanks, etc.)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Route(str, Enum):
    FAQ = "faq"
    TROUBLESHOOTING = "troubleshooting"
    DIRECT = "direct"
    TEMPLATE = "template"


@dataclass
class RouteDecision:
    route: Route
    reason: str
    confidence: float = 1.0
    existing_context: Optional[str] = None


# Intents that short-circuit to template response without hitting LLM
TEMPLATE_INTENTS = {"greeting", "thanks", "goodbye", "frustrated", "confused", "unclear"}

# Keywords that signal troubleshooting (employee-specific data needed)
# TODO Phase 5: replace with proper classifier
TROUBLESHOOTING_KEYWORDS = {
    "th": ["เงินเดือน", "หักเงิน", "ขาดงาน", "กะ", "เวลา", "ซิงค์", "attendance", "shift"],
    "en": ["attendance", "shift", "deduction", "payroll", "sync", "schedule", "not working"],
}


def decide_route(
    intent: str,
    message: str,
    language: str,
    tenant_id: str,
) -> RouteDecision:
    """Determine which path should handle this request."""
    # Template short-circuit — no LLM needed
    if intent in TEMPLATE_INTENTS:
        return RouteDecision(route=Route.TEMPLATE, reason=f"intent={intent}", confidence=1.0)

    # Troubleshooting — employee-specific data required
    msg_lower = message.lower()
    lang_key = "th" if language == "th" else "en"
    for keyword in TROUBLESHOOTING_KEYWORDS.get(lang_key, []):
        if keyword in msg_lower:
            return RouteDecision(
                route=Route.TROUBLESHOOTING,
                reason=f"keyword={keyword}",
                confidence=0.8,
            )

    # Default — FAQ RAG path
    return RouteDecision(route=Route.FAQ, reason="default", confidence=0.9)
