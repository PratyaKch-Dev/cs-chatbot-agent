"""
Query text normalization for vector search.

Handles both Thai and English:
- Lowercase
- Collapse whitespace
- Remove punctuation
- Apply Thai/EN synonym mapping
- Normalize common HR terms
"""

import re
from typing import Optional

# Thai/English synonym normalization map
# Maps colloquial terms → canonical search terms
SYNONYM_MAP: dict[str, str] = {
    # Thai
    "ถอนไม่ได้": "ถอนเงินไม่ได้",
    "เงินหาย": "ยอดเงินไม่ถูกต้อง",
    "ลืมรหัส": "ลืมรหัสผ่าน",
    # English
    "cant withdraw": "cannot withdraw",
    "money missing": "balance incorrect",
    "forgot pass": "forgot password",
    # TODO Phase 2: expand based on real user queries
}


def clean_query(text: str, language: Optional[str] = None) -> str:
    """Normalize a user query for vector search."""
    if not isinstance(text, str):
        return ""

    text = text.lower().strip()
    text = _normalize_whitespace(text)

    # Space around punctuation then collapse
    text = re.sub(r"([?.!,])", r" \1 ", text)
    text = _normalize_whitespace(text)

    # Strip leading/trailing ASCII punctuation (preserve Thai combining characters)
    text = re.sub(r"^[^\w\u0E00-\u0E7F]+|[^\w\u0E00-\u0E7F]+$", "", text)

    # Punctuation-only string → empty
    if text and re.fullmatch(r"[\W\s]+", text):
        return ""

    return _apply_synonyms(text).strip()


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _apply_synonyms(text: str) -> str:
    text_lower = text.lower()
    for colloquial, canonical in SYNONYM_MAP.items():
        text_lower = text_lower.replace(colloquial, canonical)
    return text_lower
