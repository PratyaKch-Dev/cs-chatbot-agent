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
        "th": ["สวัสดี", "หวัดดี", "ดีครับ", "ดีค่ะ", "ฮัลโหล", "หวัดดีครับ", "หวัดดีค่ะ"],
        "en": ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"],
    },
    "thanks": {
        # Explicit thanks + short affirmations / filler chitchat ("ok", "got it", "ดีๆ")
        # All of these → chitchat route, no RAG needed
        "th": [
            "ขอบคุณ", "ขอบใจ", "ขอบพระคุณ", "ขอบคุณมาก", "ขอบคุณนะ",
            "ดีๆ", "โอเค", "โอเคค่ะ", "โอเคครับ", "โอเค้", "ok", "oke",
            "เข้าใจแล้ว", "รับทราบ", "รู้แล้ว",
        ],
        "en": [
            "thank", "thanks", "appreciate", "helpful", "thx",
            "ok", "okay", "got it", "understood", "noted", "cool", "great",
        ],
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
    Returns Intent.UNCLEAR for very short messages that lack enough context.
    """
    msg_lower = message.lower().strip()
    lang_key = "th" if language == "th" else "en"

    for intent_name, lang_keywords in INTENT_KEYWORDS.items():
        keywords = lang_keywords.get(lang_key, [])
        if any(kw in msg_lower for kw in keywords):
            return IntentResult(intent=Intent(intent_name), confidence=0.9)

    # Very short message with no keywords → not enough info to answer
    if len(msg_lower) < 8:
        return IntentResult(intent=Intent.UNCLEAR, confidence=0.7)

    return IntentResult(intent=Intent.QUESTION, confidence=0.8)
