"""
CS Handoff — LLM summary + placeholder Freshchat escalation.

Flow:
  1. Build a structured prompt from active_context
  2. LLM generates a short Thai/English summary
  3. Append closing transfer message
  4. Log placeholder Freshchat escalation (real webhook wired later)
  5. Mark active_context status = "escalated"
"""

import logging
from typing import Optional

_logger = logging.getLogger("pipeline.handoff")

_HANDOFF_CLOSING_TH = "\n\nกำลังโอนให้เจ้าหน้าที่ช่วยเหลือต่อค่ะ 🙏"
_HANDOFF_CLOSING_EN = "\n\nTransferring you to a support agent now. 🙏"


# sub_type → human-readable topic for the "ปัญหา:" line in the handoff summary.
# Used both as the deterministic fallback AND to enrich the LLM prompt so the
# model never has to guess what the user's issue category is.
_SUB_TYPE_TOPIC_TH: dict[str, str] = {
    "troubleshooting_withdrawal":        "การเบิกเงินล่วงหน้า",
    "troubleshooting_money_not_arrived": "ไม่ได้รับเงินที่เบิก",
    "troubleshooting_signup":            "การลงทะเบียนเข้าใช้งาน",
    "troubleshooting_cant_find_company": "การค้นหาบริษัท",
    "troubleshooting_cant_receive_otp":  "การรับรหัส OTP",
}
_SUB_TYPE_TOPIC_EN: dict[str, str] = {
    "troubleshooting_withdrawal":        "Salary advance withdrawal",
    "troubleshooting_money_not_arrived": "Payment not received",
    "troubleshooting_signup":            "Account registration",
    "troubleshooting_cant_find_company": "Company search",
    "troubleshooting_cant_receive_otp":  "OTP not received",
}


def _topic_label(active_context: dict, language: str) -> str:
    """Return a human-readable problem label for the handoff summary."""
    sub_type = active_context.get("sub_type", "")
    table    = _SUB_TYPE_TOPIC_TH if language == "th" else _SUB_TYPE_TOPIC_EN
    if sub_type in table:
        return table[sub_type]
    # Fall back to free-form `topic` set on the context, or the user's last remark.
    return (
        active_context.get("topic", "")
        or active_context.get("remark", "")
        or ("ปัญหาที่ผู้ใช้สอบถาม" if language == "th" else "user's reported issue")
    )

_HANDOFF_SYSTEM_TH = """\
คุณคือระบบสรุปปัญหาสำหรับส่งต่อให้เจ้าหน้าที่ CS
สรุปปัญหาให้กระชับใน bullet points ภาษาไทย ไม่เกิน 4 ข้อ

รูปแบบ:
สรุปปัญหาของคุณ:
• ปัญหา: <ใช้ค่า problem_label_use_for_ปัญหา_bullet ด้านล่างเสมอ>
• FAQ ที่แนะนำแล้ว: <ถ้ามี>
• ตรวจสอบแล้ว: <ถ้ามี>
• ผลลัพธ์: <ผู้ใช้แจ้งว่า...>

ตอบเป็นสรุปเท่านั้น ไม่ต้องมีคำนำหรือคำลงท้าย"""

_HANDOFF_SYSTEM_EN = """\
You are a support issue summarizer for CS handoff.
Summarize the issue concisely in bullet points (max 4 lines).

Format:
Issue summary:
• Problem: <use the problem_label value below verbatim>
• FAQ shown: <if any>
• Checked: <if any>
• Outcome: <user says...>

Reply with the summary only — no intro, no sign-off."""


def _build_handoff_prompt(active_context: dict) -> str:
    """Build the input prompt for the LLM from active_context fields."""
    lines = []

    source   = active_context.get("source", "")
    intent   = active_context.get("intent", "")
    sub_type = active_context.get("sub_type", "")
    topic    = active_context.get("topic", "")
    remark   = active_context.get("remark", "")
    cause    = active_context.get("last_root_cause", "")
    reason   = active_context.get("handoff_reason", "")
    retries  = active_context.get("retry_count", 0)

    # Inject the deterministic topic label so the LLM ALWAYS uses it for "ปัญหา:".
    # Default language to Thai for prompt context (most users); the actual user
    # message is included separately so style is preserved.
    problem_label = _topic_label(active_context, "th")
    lines.append(f"problem_label_use_for_ปัญหา_bullet: {problem_label}")

    lines.append(f"source: {source}")
    lines.append(f"intent: {intent}")
    if sub_type:
        lines.append(f"sub_type: {sub_type}")
    if topic:
        lines.append(f"topic: {topic}")
    if remark:
        lines.append(f"user_message: {remark}")
    if cause:
        lines.append(f"last_root_cause: {cause}")
    if reason:
        lines.append(f"handoff_reason: {reason}")
    if retries:
        lines.append(f"retry_count: {retries}")

    faq_ctx = active_context.get("faq_context")
    if faq_ctx:
        lines.append(f"faq_query: {faq_ctx.get('last_query', '')}")
        score = faq_ctx.get("score")
        if score is not None:
            lines.append(f"faq_score: {score:.2f}")
        answer = faq_ctx.get("last_answer", "")
        if answer:
            lines.append(f"faq_answer_preview: {answer[:200]}")

    pending_image = active_context.get("pending_image", "")
    if pending_image:
        lines.append(f"image_context: {pending_image[:200]}")

    return "\n".join(lines)


def _llm_handoff_summary(active_context: dict, language: str) -> Optional[str]:
    """Call LLM to generate a structured handoff summary. Returns None on failure."""
    try:
        from llm.client import call_llm
        system  = _HANDOFF_SYSTEM_TH if language == "th" else _HANDOFF_SYSTEM_EN
        prompt  = _build_handoff_prompt(active_context)
        summary = call_llm(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=1024,  # Gemini Flash thinking ~600 + summary ~150
            language=language,
            step="handoff_summary",
        )
        if not summary:
            return None
        # Reject obviously truncated outputs so we fall back to deterministic.
        s = summary.strip()
        if len(s) < 30 or "สรุปปัญหา" not in s and "Issue summary" not in s:
            return None
        return s
    except Exception as e:
        _logger.warning(f"[handoff] LLM summary failed: {e}")
        return None


def _fallback_summary(active_context: dict, language: str) -> str:
    """
    Deterministic fallback when LLM is unavailable or output is unusable.
    Uses the sub_type → readable topic map so 'ปัญหา:' is always meaningful.
    """
    problem = _topic_label(active_context, language)
    reason  = active_context.get("handoff_reason", "")
    retries = active_context.get("retry_count", 0)
    cause   = active_context.get("last_root_cause", "")

    if language == "th":
        bullets = [f"• ปัญหา: {problem}"]
        if cause:
            bullets.append(f"• ตรวจสอบแล้วพบว่า: {cause}")
        if retries:
            bullets.append(f"• ผู้ใช้แจ้งปัญหาซ้ำ {retries} ครั้ง")
        if reason and not retries:
            bullets.append(f"• สาเหตุการโอน: {reason}")
        return "สรุปปัญหาของคุณ:\n" + "\n".join(bullets)

    bullets = [f"• Problem: {problem}"]
    if cause:
        bullets.append(f"• Diagnosis: {cause}")
    if retries:
        bullets.append(f"• User reported the issue {retries} time(s) after initial answer")
    if reason and not retries:
        bullets.append(f"• Reason: {reason}")
    return "Issue summary:\n" + "\n".join(bullets)


def _escalate_placeholder(tenant_id: str, user_id: str, active_context: dict) -> None:
    """
    Placeholder for Freshchat escalation API.
    Logs the escalation event — real webhook wired when Freshchat is ready.
    """
    _logger.info(
        f"[handoff] ESCALATE tenant={tenant_id} user={user_id} "
        f"intent={active_context.get('intent')} "
        f"reason={active_context.get('handoff_reason')} "
        f"retries={active_context.get('retry_count', 0)}"
    )
    # TODO: replace with Freshchat conversation escalation API call


def run_handoff_summary(
    tenant_id: str,
    user_id: str,
    active_context: dict,
    language: str,
) -> str:
    """
    Generate handoff summary, log placeholder escalation, mark context escalated.
    Returns the full message to send to the user.
    """
    summary = _llm_handoff_summary(active_context, language)
    if not summary:
        summary = _fallback_summary(active_context, language)

    closing = _HANDOFF_CLOSING_TH if language == "th" else _HANDOFF_CLOSING_EN
    full_message = summary + closing

    _escalate_placeholder(tenant_id, user_id, active_context)

    try:
        from memory.active_context import mark_escalated
        mark_escalated(tenant_id, user_id)
    except Exception as e:
        _logger.warning(f"[handoff] mark_escalated failed: {e}")

    _logger.info(f"[handoff] done tenant={tenant_id} user={user_id}")
    return full_message
