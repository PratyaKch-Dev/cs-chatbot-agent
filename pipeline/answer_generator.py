"""
Answer generator.

Produces the final response with quality controls:
    1. LLM generates answer from retrieved context / diagnostic data
    2. Grounding check scores 0–1 (how well answer is supported by context)
    3. If score < HANDOFF_THRESHOLD → trigger human handoff
    4. Otherwise → return final answer
"""

import re
from dataclasses import dataclass
from typing import Optional

from llm.client import call_llm

HANDOFF_THRESHOLD = 0.25   # word-overlap heuristic — LLM-based scorer in Phase 4

SYSTEM_PROMPT = {
    "th": (
        "คุณคือผู้ช่วย AI ของ Salary Hero สำหรับตอบคำถามด้าน HR และการเงิน\n"
        "กฎเหล็ก:\n"
        "- ใช้เฉพาะข้อมูลที่ปรากฏใน Context ด้านล่างเท่านั้น\n"
        "- ห้ามเพิ่มเติม คาดเดา หรือสร้างข้อมูลใดๆ ที่ไม่มีอยู่ใน Context โดยเด็ดขาด\n"
        "- ห้ามขึ้นต้นคำตอบด้วย 'จากข้อมูล', 'ตามข้อมูล', 'จากบริบท' หรือประโยคอ้างอิง Context ใดๆ ให้ตอบตรงๆ เลย\n"
        "- ห้ามเพิ่มหัวข้อ 'คำถามที่เกี่ยวข้อง' หรือแนะนำคำถามอื่นๆ ท้ายคำตอบ\n"
        "- ตอบเฉพาะคำถามที่ถามเท่านั้น ไม่ต้องตอบคำถามอื่นที่ไม่ได้ถาม\n"
        "- หากไม่พบคำตอบใน Context ให้ตอบว่า 'ขออภัย ไม่มีข้อมูลในส่วนนี้ กรุณาติดต่อ HR โดยตรงค่ะ'\n"
        "ตอบกระชับ ชัดเจน และเป็นมิตร"
    ),
    "en": (
        "You are Salary Hero's AI assistant for HR and payroll questions.\n"
        "Rules:\n"
        "- Use ONLY information explicitly present in the Context below.\n"
        "- Do NOT add, infer, or invent any details not found in the Context.\n"
        "- Do NOT start your answer with 'Based on the context', 'According to the context', or any similar phrasing — answer directly.\n"
        "- Do NOT add a 'Related questions' or 'You might also ask' section.\n"
        "- Answer only the question asked — nothing more.\n"
        "- If the answer is not in the Context, say: 'Sorry, I don't have that information. Please contact HR directly.'\n"
        "Be concise, clear, and friendly."
    ),
}

FALLBACK_MESSAGE = {
    "th": "ขออภัย ไม่พบข้อมูลที่เกี่ยวข้อง กรุณาติดต่อฝ่าย HR โดยตรงค่ะ",
    "en": "Sorry, I couldn't find relevant information. Please contact HR directly.",
}


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
    """Generate a grounded answer and optionally escalate."""
    lang = language if language in ("th", "en") else "th"

    if not context:
        return GeneratedAnswer(
            text=FALLBACK_MESSAGE[lang],
            grounding_score=0.0,
            was_escalated=True,
            route_taken=route,
        )

    user_prompt = (
        f"Context:\n{context}\n\n"
        f"Question: {message}"
    )

    messages = list(history) + [{"role": "user", "content": user_prompt}]
    answer = call_llm(messages=messages, system=SYSTEM_PROMPT[lang], language=lang)
    answer = _clean_answer(answer)

    score = _score_grounding(answer, context)
    escalate = score < HANDOFF_THRESHOLD

    return GeneratedAnswer(
        text=answer if not escalate else FALLBACK_MESSAGE[lang],
        grounding_score=score,
        was_escalated=escalate,
        handoff_context={"original_message": message, "context": context} if escalate else None,
        route_taken=route,
    )


_PREAMBLE_RE = re.compile(
    # Thai: strip only when preamble is clearly separated by , : or newline
    # e.g. "จากข้อมูลใน Context:" or "ตามข้อมูลที่ระบุ,"
    # NOT "ตามข้อมูลที่ระบุ กรณี..." (no separator = actual answer content)
    r"^(จาก|ตาม)(ข้อมูล|บริบท)[^\n:,،]{0,30}[:\n,،]\s*"
    r"|^(based on|according to)\s+the\s+(provided\s+)?context[^\n:,]{0,30}[:\n,]\s*",
    re.IGNORECASE,
)


_RELATED_RE = re.compile(
    r"\n*\**(เกี่ยวกับ)?คำถามที่เกี่ยวข้อง\**[^\n]*:?.*$"
    r"|\n*(related questions?|you might also ask)[^\n]*:?.*$",
    re.IGNORECASE | re.DOTALL,
)


def _clean_answer(answer: str) -> str:
    """Strip preamble and related-questions section the LLM sometimes adds."""
    answer = _PREAMBLE_RE.sub("", answer).lstrip()
    answer = _RELATED_RE.sub("", answer).rstrip()
    return answer


def _score_grounding(answer: str, context: str) -> float:
    """
    Score how well the answer is grounded in the context.
    Uses word overlap as a lightweight heuristic.
    """
    if not context or not answer:
        return 0.0

    # Extract meaningful words (length > 2) from context and answer
    context_words = set(re.findall(r"\w{3,}", context.lower()))
    answer_words = set(re.findall(r"\w{3,}", answer.lower()))

    if not answer_words:
        return 0.0

    overlap = answer_words & context_words
    return min(len(overlap) / max(len(answer_words), 1), 1.0)
