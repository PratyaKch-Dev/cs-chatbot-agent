"""
Request router.

Decides which pipeline path handles the request:
    - faq          → LangChain RAG retrieval
    - troubleshooting → LangChain ReAct agent with tools
    - direct       → Answer generation with existing context
    - template     → Pre-written template response (greeting, thanks, etc.)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Route(str, Enum):
    FAQ = "faq"
    TROUBLESHOOTING = "troubleshooting"
    DIRECT = "direct"
    TEMPLATE = "template"


@dataclass
class RouteDecision:
    route: Route
    reason: str
    confidence: float = 1.0
    existing_context: Optional[str] = None


# Intents that short-circuit to template response without hitting LLM
TEMPLATE_INTENTS = {"greeting", "thanks", "goodbye", "frustrated", "confused", "unclear"}

# Keywords that signal troubleshooting (employee-specific data needed)
# TODO Phase 5: replace with proper classifier
TROUBLESHOOTING_KEYWORDS = {
    "th": [
        # withdrawal / balance issues
        "เบิกไม่ได้", "เบิกเงินไม่ได้", "ยอด 0", "ยอด0", "0 บาท", "0บาท",
        "แสดง 0", "แสดงผล 0", "ไม่มียอด", "ยอดไม่ขึ้น", "เงินไม่ขึ้น",
        "เบิกไม่ผ่าน", "ทำไมเบิกไม่ได้",
        "ยอดเบิก", "เป็น 0", "เป็น0", "ยอดเป็น 0", "ยอดเป็น0",
        # account / system issues
        "เงินเดือน", "หักเงิน", "ขาดงาน", "กะ", "ซิงค์", "ลงทะเบียน",
        "สถานะ", "บัญชีถูก", "ระงับ",
        # attendance queries — needs live employee data, not FAQ
        "การเข้างาน", "เข้างาน", "check in", "check out", "เช็คอิน", "เช็คเอาท์",
        "ประวัติการเข้างาน", "ประวัติเข้างาน", "บันทึกเวลา", "ลืม punch",
        "สายกี่วัน", "ขาดกี่วัน", "มาสาย",
    ],
    "en": [
        "can't withdraw", "cannot withdraw", "zero balance", "balance 0",
        "withdrawal failed", "not eligible",
        "attendance", "check in", "check out", "punch in", "punch out",
        "attendance record", "attendance history", "missed punch",
        "deduction", "payroll", "sync", "schedule", "not working",
    ],
}


def decide_route(
    intent: str,
    message: str,
    language: str,
    tenant_id: str,
) -> RouteDecision:
    """Determine which path should handle this request."""
    # Template short-circuit — no LLM needed
    if intent in TEMPLATE_INTENTS:
        return RouteDecision(route=Route.TEMPLATE, reason=f"intent={intent}", confidence=1.0)

    # Troubleshooting — employee-specific data required
    msg_lower = message.lower()
    lang_key = "th" if language == "th" else "en"
    for keyword in TROUBLESHOOTING_KEYWORDS.get(lang_key, []):
        if keyword in msg_lower:
            return RouteDecision(
                route=Route.TROUBLESHOOTING,
                reason=f"keyword={keyword}",
                confidence=0.8,
            )

    # Default — FAQ RAG path
    return RouteDecision(route=Route.FAQ, reason="default", confidence=0.9)
