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
    """
    Determine which path should handle this request.

    TODO Phase 3: implement FAQ vs troubleshooting classification.
    TODO Phase 5: wire troubleshooting keyword/classifier logic.
    """
    raise NotImplementedError("Phase 3")
