"""
Main pipeline orchestrator.

Single entry point for all interfaces (Gradio, LINE webhook, future APIs).
Coordinates: session → memory → route → pipeline → save.

Usage:
    from pipeline.orchestrator import handle_message

    result = handle_message(
        tenant_id="hns",
        user_id="U1234",          # LINE user ID or employee ID
        message="เบิกเงินไม่ได้",
        employee_id="EMP003",     # for troubleshooting API calls
    )
    reply = result.answer
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from pipeline.router import decide_route, Route
from rag.retriever import retrieve, build_context
from pipeline.answer_generator import generate_answer, SYSTEM_PROMPT
from utils.language import detect_language
from utils.pipeline_logger import PipelineTrace
from llm.intent import detect_intent

from memory.history import load_history, save_turn, clear_history
from memory.session import get_or_create_session, touch_session, end_session
from memory.context_cache import (
    save_faq_context, save_diagnostic_context,
    load_faq_context, load_context, clear_context,
)
from memory.summarizer import load_summary, clear_summary, update_rolling_summary_async
import memory.active_context as ac

_logger = logging.getLogger("pipeline.orchestrator")

_TS_TOPIC = {
    "troubleshooting_withdrawal": "withdrawal_issue",
    # Add new subtypes here when ready: "troubleshooting_payslip": "payslip_issue", etc.
}

TROUBLESHOOTING_SYSTEM_PROMPT = {
    "th": (
        "คุณคือผู้ช่วย AI ของ Salary Hero สำหรับแก้ปัญหาเฉพาะบุคคล\n"
        "ตอบโดยอ้างอิงจากข้อมูลการวินิจฉัยที่ให้มาเท่านั้น\n"
        "ระบุสาเหตุและแนวทางแก้ไขให้ชัดเจน กระชับ และเป็นมิตร\n"
        "ห้ามขึ้นต้นด้วย 'จากข้อมูล' หรือ 'ตามข้อมูล'\n"
        "ห้ามเพิ่มหัวข้อ 'คำถามที่เกี่ยวข้อง' ท้ายคำตอบ"
    ),
    "en": (
        "You are Salary Hero's AI assistant for individual troubleshooting.\n"
        "Answer strictly based on the diagnostic data provided.\n"
        "Clearly state the root cause and resolution steps. Be concise and friendly.\n"
        "Do NOT start with 'Based on the data' or similar preambles.\n"
        "Do NOT add a 'Related questions' section."
    ),
}


@dataclass
class MessageResult:
    answer: str
    trace: Optional[str] = None
    image_urls: list = field(default_factory=list)
    was_escalated: bool = False


def _build_system_with_summary(base_system: str, summary: str) -> str:
    if not summary:
        return base_system
    return (
        f"{base_system}\n\n"
        f"--- Previous session context ---\n{summary}\n"
        f"--- End of previous context ---"
    )


def handle_message(
    tenant_id: str,
    user_id: str,
    message: str,
    employee_id: str = "",
    return_trace: bool = False,
) -> MessageResult:
    """
    Full pipeline entry point. Called by all interfaces.

    Args:
        tenant_id:    Company namespace (e.g. "hns")
        user_id:      LINE user ID (webhook) or employee ID (Gradio testing)
        message:      Raw user message text
        employee_id:  Employee ID for troubleshooting API calls.
                      Falls back to user_id if not provided.
        return_trace: Whether to include pipeline trace in result.
    """
    if not message.strip():
        return MessageResult(answer="")

    emp_id   = employee_id or user_id
    language = detect_language(message)
    trace    = PipelineTrace(tenant_id=tenant_id, query=message, language=language)

    # ── Load memory ───────────────────────────────────────────────────────────
    get_or_create_session(tenant_id, user_id)
    redis_history  = load_history(tenant_id, user_id, language)
    summary        = load_summary(tenant_id, user_id, language)
    cached_ctx     = load_context(tenant_id, user_id)
    active_ctx     = ac.load(tenant_id, user_id)
    active_ctx_str = ac.load_for_router(tenant_id, user_id)

    trace.set_memory(
        history=redis_history,
        summary=summary,
        context_type=cached_ctx.get("type", "") if cached_ctx else "",
        context_detail=(
            cached_ctx.get("root_cause", "") if cached_ctx and cached_ctx.get("type") == "troubleshooting"
            else cached_ctx.get("question", "")[:60] if cached_ctx else ""
        ),
    )

    # ── Route ─────────────────────────────────────────────────────────────────
    intent_result = detect_intent(message, language)
    decision = decide_route(
        intent_result.intent, message, language, tenant_id,
        recent_history=redis_history,
        active_context=active_ctx_str,
        summary=summary,
    )

    # ── Path execution ─────────────────────────────────────────────────────────

    # Active troubleshooting case check
    _active_is_ts = (
        active_ctx is not None
        and active_ctx.get("intent") == "troubleshooting"
        and active_ctx.get("status") == "active"
    )
    # Recheck if router says so, OR active TS case + follow-up/ambiguous message
    _is_ts_recheck = (
        decision.followup_type == "troubleshooting_recheck"
        or (_active_is_ts and decision.conv_state in ("followup", "ambiguous"))
    )

    if _is_ts_recheck:
        answer = _run_troubleshooting_recheck(
            message, language, tenant_id, user_id, emp_id,
            active_ctx, decision, redis_history, summary, trace,
        )

    elif decision.conv_state == "followup" and decision.followup_type == "faq_followup":
        answer = _run_faq_followup(
            message, language, tenant_id, user_id,
            active_ctx, decision, redis_history, summary, trace,
        )

    elif decision.route == Route.CHITCHAT:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
        answer = generate_answer(
            message=message, context="", language=language,
            tenant_id=tenant_id, intent=intent_result.intent.value,
            history=redis_history, route=str(decision.route),
            template_key=decision.template_key,
        )

    elif decision.route == Route.MISSING_INFO:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
        answer = generate_answer(
            message=message, context="", language=language,
            tenant_id=tenant_id, intent=intent_result.intent.value,
            history=redis_history, route=str(decision.route),
            template_key=decision.template_key,
        )

    elif decision.route == Route.TROUBLESHOOTING:
        answer = _run_troubleshooting_new(
            message, language, tenant_id, user_id, emp_id,
            decision, redis_history, summary, trace,
        )

    else:
        answer = _run_faq(
            message, language, tenant_id, user_id,
            decision, redis_history, summary, trace,
        )

    # ── Persist ───────────────────────────────────────────────────────────────
    save_turn(tenant_id, user_id, language, message, answer.text)
    touch_session(tenant_id, user_id)

    # Goodbye → clear session state (keep summary for next session)
    if decision.route == Route.CHITCHAT and decision.template_key in ("goodbye", "thanks"):
        clear_history(tenant_id, user_id, language)
        clear_context(tenant_id, user_id)
        ac.clear(tenant_id, user_id)
        end_session(tenant_id, user_id)

    # Rolling summary runs in background — zero latency impact
    update_rolling_summary_async(tenant_id, user_id, language, message, answer.text)

    # ── Trace ─────────────────────────────────────────────────────────────────
    trace.set_answer(
        text=answer.text,
        grounding_score=answer.grounding_score,
        was_escalated=answer.was_escalated,
    )
    trace.flush()

    return MessageResult(answer=answer.text, image_urls=answer.image_urls, was_escalated=answer.was_escalated)


# ── Pipeline sub-handlers ────────────────────────────────────────────────��────

def _run_troubleshooting_recheck(
    message, language, tenant_id, user_id, emp_id,
    active_ctx, decision, redis_history, summary, trace,
):
    from agent.planner import run_troubleshooting_agent
    recheck_emp_id  = (active_ctx or {}).get("employee_id") or emp_id
    recheck_subtype = (active_ctx or {}).get("sub_type") or decision.template_key

    trace.set_route(route="Route.TROUBLESHOOTING", reason=f"recheck: {decision.reason}")
    agent_result = run_troubleshooting_agent(
        employee_id=recheck_emp_id, issue=message, language=language,
        tenant_id=tenant_id, sub_type=recheck_subtype,
    )
    trace.set_troubleshooting(
        employee_id=recheck_emp_id,
        root_cause=agent_result["root_cause"],
        tools_used=agent_result["tools_used"],
    )
    diag = agent_result["diagnostic_context"]
    save_diagnostic_context(tenant_id, user_id, employee_id=recheck_emp_id,
                            diagnostic_context=diag, root_cause=agent_result["root_cause"])
    ac.save_troubleshooting_context(
        tenant_id, user_id,
        topic=_TS_TOPIC.get(recheck_subtype, recheck_subtype),
        sub_type=recheck_subtype,
        remark=message,
        employee_id=recheck_emp_id, last_root_cause=agent_result["root_cause"],
    )
    system = _build_system_with_summary(
        TROUBLESHOOTING_SYSTEM_PROMPT.get(language, TROUBLESHOOTING_SYSTEM_PROMPT["th"]), summary)
    return generate_answer(
        message=message, context=diag, language=language, tenant_id=tenant_id,
        intent="question", history=redis_history, route="Route.TROUBLESHOOTING",
        system_prompt_override=system, prefilled_answer=agent_result.get("template_answer", ""),
    )


def _run_troubleshooting_new(
    message, language, tenant_id, user_id, emp_id,
    decision, redis_history, summary, trace,
):
    from agent.planner import run_troubleshooting_agent
    trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
    agent_result = run_troubleshooting_agent(
        employee_id=emp_id, issue=message, language=language,
        tenant_id=tenant_id, sub_type=decision.template_key,
    )
    trace.set_troubleshooting(
        employee_id=emp_id,
        root_cause=agent_result["root_cause"],
        tools_used=agent_result["tools_used"],
    )
    diag = agent_result["diagnostic_context"]
    save_diagnostic_context(tenant_id, user_id, employee_id=emp_id,
                            diagnostic_context=diag, root_cause=agent_result["root_cause"])
    ac.save_troubleshooting_context(
        tenant_id, user_id,
        topic=_TS_TOPIC.get(decision.template_key, decision.template_key),
        sub_type=decision.template_key,
        remark=message, employee_id=emp_id, last_root_cause=agent_result["root_cause"],
    )
    system = _build_system_with_summary(
        TROUBLESHOOTING_SYSTEM_PROMPT.get(language, TROUBLESHOOTING_SYSTEM_PROMPT["th"]), summary)
    return generate_answer(
        message=message, context=diag, language=language, tenant_id=tenant_id,
        intent="question", history=redis_history, route=str(decision.route),
        system_prompt_override=system, prefilled_answer=agent_result.get("template_answer", ""),
    )


def _run_faq_followup(
    message, language, tenant_id, user_id,
    active_ctx, decision, redis_history, summary, trace,  # noqa: ARG001 active_ctx kept for signature compat
):
    rag_query = decision.search_query or message
    trace.set_route(route=str(Route.FAQ), reason=f"faq_followup: {decision.reason}")
    _t0 = time.perf_counter()
    result = retrieve(rag_query, tenant_id, language, top_k=3)
    trace.mark_step("retrieval", (time.perf_counter() - _t0) * 1000)
    q_label = f"[rewrite] {result.query_used}" if decision.search_query else f"[followup] {result.query_used}"
    trace.set_retrieval(query_used=q_label, collection=result.collection, documents=result.documents)

    context   = build_context(result.documents, language)
    top_score = result.documents[0].score if result.documents else 0.0

    # Always inject previous FAQ answer — it's always relevant for follow-ups
    cached_faq = load_faq_context(tenant_id, user_id)
    if cached_faq:
        prev = (f"[Previous answer on related topic]\n"
                f"Q: {cached_faq['question']}\nA: {cached_faq['answer']}\n\n")
        context = prev + context if context else prev

    from pipeline.answer_generator import FOLLOWUP_SYSTEM_PROMPT
    base   = FOLLOWUP_SYSTEM_PROMPT.get(language, FOLLOWUP_SYSTEM_PROMPT["th"])
    system = _build_system_with_summary(base, summary)
    answer = generate_answer(
        message=message, context=context, language=language, tenant_id=tenant_id,
        intent="question", history=redis_history, route=str(Route.FAQ),
        top_retrieval_score=max(top_score, 0.45) if cached_faq else top_score,
        system_prompt_override=system,
    )
    if result.documents and result.documents[0].image_urls:
        answer.image_urls = result.documents[0].image_urls
    save_faq_context(tenant_id, user_id, question=message,
                     retrieved_docs=[d.answer for d in result.documents], answer=answer.text)
    ac.update_remark(tenant_id, user_id, message)
    return answer


def _run_faq(
    message, language, tenant_id, user_id,
    decision, redis_history, summary, trace,
):
    cached_faq = load_faq_context(tenant_id, user_id)
    rag_query  = decision.search_query or message

    trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
    _t0 = time.perf_counter()
    result = retrieve(rag_query, tenant_id, language, top_k=3)
    trace.mark_step("retrieval", (time.perf_counter() - _t0) * 1000)
    q_label = f"[rewrite] {result.query_used}" if decision.search_query else result.query_used
    trace.set_retrieval(query_used=q_label, collection=result.collection, documents=result.documents)

    context   = build_context(result.documents, language)
    top_score = result.documents[0].score if result.documents else 0.0
    top_doc   = result.documents[0] if result.documents else None

    # High-confidence match: return the article answer + image verbatim.
    # Articles with images: the image IS the answer — always direct-pass, LLM must not be in the middle.
    # Text-only articles: require gap ≥ 0.05 vs rank #2 to avoid returning wrong article when two are close.
    _rank2_score = result.documents[1].score if len(result.documents) > 1 else 0.0
    _gap = top_score - _rank2_score
    _has_image = bool(top_doc and top_doc.image_urls)
    if top_doc and top_score >= 0.45 and not cached_faq and (_has_image or _gap >= 0.05):
        from pipeline.answer_generator import GeneratedAnswer
        answer = GeneratedAnswer(
            text=top_doc.answer,
            grounding_score=1.0,
            was_escalated=False,
            route_taken=str(decision.route),
            image_urls=top_doc.image_urls,
        )
        save_faq_context(tenant_id, user_id, question=message,
                         retrieved_docs=[d.answer for d in result.documents], answer=answer.text)
        ac.save_faq_context(tenant_id, user_id, topic=message[:60],
                            remark=message, last_user_need=message)
        return answer

    if cached_faq and top_score < 0.6:
        prev = (f"[Previous answer on related topic]\n"
                f"Q: {cached_faq['question']}\nA: {cached_faq['answer']}\n\n")
        context = prev + context if context else prev

    system = _build_system_with_summary(SYSTEM_PROMPT.get(language, SYSTEM_PROMPT["th"]), summary)
    answer = generate_answer(
        message=message, context=context, language=language, tenant_id=tenant_id,
        intent="question", history=redis_history, route=str(decision.route),
        top_retrieval_score=top_score, system_prompt_override=system,
    )
    if top_doc and top_doc.image_urls:
        answer.image_urls = top_doc.image_urls
    save_faq_context(tenant_id, user_id, question=message,
                     retrieved_docs=[d.answer for d in result.documents], answer=answer.text)
    ac.save_faq_context(tenant_id, user_id, topic=message[:60],
                        remark=message, last_user_need=message)
    return answer
