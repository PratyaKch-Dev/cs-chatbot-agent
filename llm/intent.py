"""
Intent detection.

Keyword-based classification of user intent.
Runs before routing to short-circuit simple interactions (greetings, thanks)
without hitting the full RAG pipeline.

Intent types:
    greeting, thanks, goodbye, frustrated, confused, unclear, question
"""

from enum import Enum
from dataclasses import dataclass


class Intent(str, Enum):
    GREETING = "greeting"
    THANKS = "thanks"
    GOODBYE = "goodbye"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    UNCLEAR = "unclear"
    QUESTION = "question"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float = 1.0


INTENT_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "th": ["สวัสดี", "หวัดดี", "ดีครับ", "ดีค่ะ", "ฮัลโหล"],
        "en": ["hello", "hi", "hey", "good morning", "good afternoon"],
    },
    "thanks": {
        "th": ["ขอบคุณ", "ขอบใจ", "ขอบพระคุณ", "โอเค ขอบคุณ"],
        "en": ["thank", "thanks", "appreciate", "helpful"],
    },
    "goodbye": {
        "th": ["ลาก่อน", "บ๊าย", "บาย", "แล้วเจอกัน"],
        "en": ["bye", "goodbye", "see you", "take care"],
    },
    "frustrated": {
        "th": ["หัวร้อน", "รำคาญ", "แย่มาก", "ไม่ได้เรื่อง", "ห่วย", "โกรธ"],
        "en": ["frustrated", "angry", "terrible", "useless", "fed up", "ridiculous"],
    },
    "confused": {
        "th": ["งงมาก", "ไม่เข้าใจ", "งง", "หมายความว่าอะไร"],
        "en": ["confused", "don't understand", "what do you mean", "unclear"],
    },
}


def detect_intent(message: str, language: str) -> IntentResult:
    """
    Classify the intent of a user message using keyword matching.

    Falls back to Intent.QUESTION if no pattern matches.

    TODO Phase 2: implement keyword matching logic.
    """
    raise NotImplementedError("Phase 2")
