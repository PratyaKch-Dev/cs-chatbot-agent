"""Language detection — Thai vs English."""

import re


def detect_language(text: str) -> str:
    """Detect whether text is Thai or English based on character presence."""
    if re.search(r"[\u0E00-\u0E7F]", text):
        return "th"
    return "en"
