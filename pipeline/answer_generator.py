"""
Answer generator.

Produces the final response with quality controls:
    1. LLM generates answer from retrieved context / diagnostic data
    2. Grounding check scores 0–1 (how well answer is supported by context)
    3. If score < HANDOFF_THRESHOLD → trigger human handoff
    4. Otherwise → return final answer
"""

from dataclasses import dataclass
from typing import Optional

HANDOFF_THRESHOLD = 0.65   # escalate to human if grounding score below this


@dataclass
class GeneratedAnswer:
    text: str
    grounding_score: float          # 0.0 – 1.0
    was_escalated: bool = False
    handoff_context: Optional[dict] = None
    route_taken: str = ""


def generate_answer(
    message: str,
    context: str,
    language: str,
    tenant_id: str,
    intent: str,
    history: list[dict],
    route: str,
) -> GeneratedAnswer:
    """
    Generate a grounded answer and optionally escalate.

    TODO Phase 3: implement LLM call + grounding scorer.
    TODO Phase 3: wire handoff.build_handoff_context on escalation.
    """
    raise NotImplementedError("Phase 3")


def _score_grounding(answer: str, context: str) -> float:
    """
    Score how well the answer is supported by the retrieved context.
    Returns a float between 0.0 (not grounded) and 1.0 (fully grounded).

    TODO Phase 3: implement LLM-based or keyword-overlap grounding scorer.
    """
    raise NotImplementedError("Phase 3")
