"""
Language detection.

Identifies whether a message is Thai or English.
Falls back to Thai ('th') if detection is uncertain.

NOTE: Currently returns hardcoded 'th' — real implementation in Phase 2.
"""

SUPPORTED_LANGUAGES = {"th", "en"}
DEFAULT_LANGUAGE = "th"


def detect_language(text: str) -> str:
    """
    Detect the language of a text string.
    Returns ISO 639-1 code: 'th' or 'en'.

    TODO Phase 2: implement using PyThaiNLP + langdetect.
    Currently hardcoded to 'th'.
    """
    # TODO Phase 2: replace with real detection
    return DEFAULT_LANGUAGE


def is_thai(text: str) -> bool:
    """Return True if text contains Thai characters."""
    return any("\u0e00" <= char <= "\u0e7f" for char in text)
