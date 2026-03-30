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
    """
    Evaluate whether a message is safe and in-scope.

    TODO Phase 3: implement keyword blocking + LLM-based policy check.
    """
    raise NotImplementedError("Phase 3")
