"""
Safety and policy check.

Filters requests that are:
- Harmful or abusive
- Off-topic (not related to HR / salary / work)
- Policy-violating (prompt injection, jailbreak attempts)

Runs before routing so no pipeline resources are spent on blocked requests.
"""

from dataclasses import dataclass


@dataclass
class SafetyResult:
    is_safe: bool
    reason: str = ""
    category: str = ""   # harmful | off_topic | policy_violation | safe


# Keywords that are always blocked regardless of language
BLOCKED_PATTERNS: list[str] = [
    # TODO Phase 3: populate with actual policy patterns
]

# Topics in scope for this bot
IN_SCOPE_KEYWORDS = {
    "th": ["เงิน", "เงินเดือน", "ถอน", "กะ", "ลา", "บัญชี", "โบนัส", "ประกัน"],
    "en": ["salary", "withdraw", "shift", "leave", "account", "bonus", "insurance", "payroll"],
}


def check_safety(message: str, language: str) -> SafetyResult:
    """Evaluate whether a message is safe and in-scope."""
    msg_lower = message.lower().strip()

    # Block explicitly harmful patterns
    for pattern in BLOCKED_PATTERNS:
        if pattern in msg_lower:
            return SafetyResult(is_safe=False, reason=f"blocked pattern: {pattern}", category="harmful")

    # Check if message is in scope (has at least one relevant keyword)
    lang_key = "th" if language == "th" else "en"
    in_scope = any(kw in msg_lower for kw in IN_SCOPE_KEYWORDS.get(lang_key, []))

    # Very short messages (greetings etc.) are always allowed through
    if not in_scope and len(msg_lower.split()) > 5:
        return SafetyResult(is_safe=False, reason="off-topic", category="off_topic")

    return SafetyResult(is_safe=True, category="safe")
