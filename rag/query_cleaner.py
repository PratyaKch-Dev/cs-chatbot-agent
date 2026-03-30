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
    """
    Normalize a user query for vector search.

    TODO Phase 2: implement full normalization pipeline.
    """
    raise NotImplementedError("Phase 2")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _apply_synonyms(text: str) -> str:
    text_lower = text.lower()
    for colloquial, canonical in SYNONYM_MAP.items():
        text_lower = text_lower.replace(colloquial, canonical)
    return text_lower
