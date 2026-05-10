"""
Image intent classifier.

Given a vision-generated image description, return a likely intent label
plus 2-3 suggested clarifying replies in the user's language. Pure keyword
matching against config/image_intents.yaml — fast, no LLM call, no network.

Used by pipeline.image_handler when the user sends an image without text,
to build a clarifying question with helpful options.
"""

from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "image_intents.yaml"

_intents_cache: Optional[list[dict]] = None


def _intents() -> list[dict]:
    global _intents_cache
    if _intents_cache is None:
        with open(_CONFIG_PATH) as f:
            _intents_cache = yaml.safe_load(f).get("intents", [])
    return _intents_cache


def classify_image_intent(description: str, language: str = "th") -> tuple[str, list[str]]:
    """
    Match keywords against the description and return (intent_id, suggestions).
    Falls back to "generic" if nothing matches.
    """
    text = (description or "").lower()
    kw_field = "keywords_th" if language == "th" else "keywords_en"
    sg_field = "suggestions_th" if language == "th" else "suggestions_en"

    fallback = ("generic", [])
    for intent in _intents():
        intent_id = intent.get("id", "")
        if intent_id == "generic":
            fallback = (intent_id, intent.get(sg_field, []))
            continue
        for kw in intent.get(kw_field, []):
            if kw and kw.lower() in text:
                return intent_id, intent.get(sg_field, [])

    return fallback
