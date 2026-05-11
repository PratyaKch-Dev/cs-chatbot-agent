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

import os
import time
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from pipeline.router import decide_route, Route, RouteDecision
from pipeline.context_resolver import resolve as _resolve, FlowAction  # noqa: F401 (FlowAction kept for compat)
from pipeline.handoff import run_handoff_summary
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
from memory.pending_image import clear_pending_image
from memory.summarizer import load_summary, clear_summary, update_rolling_summary_async
import memory.active_context as ac
from llm.templates import IMAGE_CAPTION_PREFIX, append_confirmation, get_template, GLAD_TO_HELP

# ── Load troubleshooting flow config ─────────────────────────────────────────
_FLOWS_PATH = Path(__file__).parent.parent / "config" / "troubleshooting_flows.yaml"

def _load_flows() -> tuple[dict, dict]:
    with open(_FLOWS_PATH) as f:
        raw = yaml.safe_load(f)
    global_cfg = raw.get("global", {})
    flows      = {k: v for k, v in raw.items() if k != "global"}
    return global_cfg, flows

_GLOBAL_CFG, _FLOWS = _load_flows()


@dataclass
class StageInput:
    message:        str
    enriched_query: str
    pending_image:  str
    active_context: dict
    language:       str
    tenant_id:      str
    user_id:        str
    emp_id:         str
    access_token:   str
    history:        list[dict]
    summary:        str

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


# Fallback messages emitted when the LLM has no usable info.
# Never attach images or persist context when the reply is one of these.
_FALLBACK_SUBSTRINGS = ("ไม่มีข้อมูลในส่วนนี้", "ไม่พบข้อมูลที่เกี่ยวข้อง")


def _is_fallback_answer(text: str) -> bool:
    return any(s in text for s in _FALLBACK_SUBSTRINGS)


def _answer_uses_doc(answer_text: str, doc_answer: str, min_overlap: float = 0.30) -> bool:
    """
    True if `answer_text` shares substantial content with `doc_answer`.
    Used to gate image attachment: when the LLM generates a novel answer
    (e.g. "download from App Store / Play Store") that doesn't actually
    use the top retrieved doc, we must NOT attach that doc's image.

    Uses character 5-grams — robust for Thai which has no word boundaries.
    """
    if not answer_text or not doc_answer:
        return False
    import re
    def _ngrams(s: str, n: int = 5) -> set:
        s = re.sub(r"\s+", "", s)
        return {s[i:i+n] for i in range(len(s) - n + 1)}
    a = _ngrams(answer_text)
    d = _ngrams(doc_answer)
    if not a:
        return False
    return len(a & d) / len(a) >= min_overlap


def _build_system_with_summary(base_system: str, summary: str) -> str:
    if not summary:
        return base_system
    return (
        f"{base_system}\n\n"
        f"--- Previous session context ---\n{summary}\n"
        f"--- End of previous context ---"
    )


def _prepend_image_situation(context: str, image_situation: str, language: str) -> str:
    """
    Prepend image-derived situation to retrieval context so the LLM treats it
    as authoritative grounding alongside the retrieved FAQ docs.
    """
    if language == "th":
        label = (
            "[สถานการณ์เฉพาะของผู้ใช้จากภาพหน้าจอที่แนบมา — ใช้เป็นข้อมูลหลักในการตอบ]"
        )
    else:
        label = (
            "[User's specific situation shown in the attached screenshot "
            "— treat as primary grounding for the answer]"
        )
    block = f"{label}\n{image_situation}\n\n"
    return block + context if context else block


def handle_message(
    tenant_id: str,
    user_id: str,
    message: str,
    employee_id: str = "",
    access_token: str = "",
    return_trace: bool = False,
) -> MessageResult:
    """
    Full pipeline entry point. Called by all interfaces.

    Args:
        tenant_id:    Company namespace (e.g. "hns")
        user_id:      LINE user ID (webhook) or display ID (Gradio testing)
        message:      Raw user message text
        employee_id:  Override employee ID (optional — mainly for testing).
        access_token: Token from mobile app. Mock phase: pass employee_id string
                      (e.g. "EMP001"). Real phase: Salary Hero Bearer token;
                      BE derives the user from it — chatbot never trusts emp_id directly.
        return_trace: Whether to include pipeline trace in result.
    """
    if not message.strip():
        return MessageResult(answer="")

    # Mock phase: access_token = employee_id string (e.g. "EMP001").
    # Real phase: access_token = Bearer token; BE derives employee from it.
    emp_id = employee_id or access_token or user_id

    language = detect_language(message)
    trace    = PipelineTrace(tenant_id=tenant_id, query=message, language=language)

    # ── Context Resolver — loads all memory, interprets flow_action ───────────
    # pending_image is loaded inside resolve() and returned as resolution.pending_image.
    # It is applied or discarded AFTER the router call based on decision.is_new.
    get_or_create_session(tenant_id, user_id)
    resolution     = _resolve(tenant_id, user_id, message, language)
    redis_history  = resolution.history
    summary        = resolution.summary
    active_ctx     = resolution.active_context
    active_ctx_str = ac.load_for_router(tenant_id, user_id)
    cached_ctx     = load_context(tenant_id, user_id)

    _logger.info(
        f"[orchestrator] resolver={resolution.flow_action.value} "
        f"reason={resolution.resolver_reason} intent={resolution.active_intent!r}"
    )
    trace.set_resolver(action=resolution.flow_action.value, reason=resolution.resolver_reason)

    trace.set_memory(
        history=redis_history,
        summary=summary,
        context_type=cached_ctx.get("type", "") if cached_ctx else "",
        context_detail=(
            cached_ctx.get("root_cause", "") if cached_ctx and cached_ctx.get("type") == "troubleshooting"
            else cached_ctx.get("question", "")[:60] if cached_ctx else ""
        ),
    )

    # ── FlowAction early exits — deterministic, no LLM needed ─────────────────

    if resolution.flow_action == FlowAction.END_FLOW:
        _logger.info(f"[orchestrator] END_FLOW → glad_to_help")
        ac.mark_resolved(tenant_id, user_id)
        answer_text = get_template(GLAD_TO_HELP, language)
        save_turn(tenant_id, user_id, language, message, answer_text)
        touch_session(tenant_id, user_id)
        update_rolling_summary_async(tenant_id, user_id, language, message, answer_text)
        trace.flush()
        return MessageResult(answer=answer_text)

    if resolution.flow_action == FlowAction.TRIGGER_HANDOFF:
        # Explicit user-requested handoff (clicked "ต้องการโอน") fires immediately
        # regardless of retry_count or active topic.
        if resolution.resolver_reason == "user_requested_handoff":
            _logger.info("[orchestrator] user requested handoff → escalating now")
            answer_text = run_handoff_summary(tenant_id, user_id, active_ctx, language)
            save_turn(tenant_id, user_id, language, message, answer_text)
            touch_session(tenant_id, user_id)
            update_rolling_summary_async(tenant_id, user_id, language, message, answer_text)
            trace.flush()
            return MessageResult(answer=answer_text, was_escalated=True)

        retry_count = active_ctx.get("retry_count", 0) + 1
        ac.patch(tenant_id, user_id, retry_count=retry_count)
        active_ctx["retry_count"] = retry_count

        # Recheck instead of auto-handoff: keep diagnosing on every "ยังไม่ได้".
        # After MAX_TROUBLESHOOTING_RETRIES, the post-processing block below
        # appends the "ต้องการโอนไป" option so the user can opt into handoff.
        is_troubleshooting = active_ctx.get("intent") == "troubleshooting"
        if is_troubleshooting:
            _logger.info(
                f"[orchestrator] TRIGGER_HANDOFF on troubleshooting → "
                f"recheck attempt {retry_count}"
            )
            recheck_decision = RouteDecision(
                route=Route.TROUBLESHOOTING,
                reason=f"recheck#{retry_count} after unresolved",
                template_key=active_ctx.get("sub_type", "troubleshooting_withdrawal"),
                is_new=False,
            )
            answer = _run_troubleshooting_recheck(
                message, language, tenant_id, user_id, emp_id,
                active_ctx, recheck_decision, redis_history, summary, trace,
                access_token=access_token,
            )
            # Once the user has retried >= MAX times, surface the explicit
            # "transfer to agent" option in the confirmation prompt instead
            # of auto-escalating. The user stays in control.
            with_transfer = retry_count >= MAX_TROUBLESHOOTING_RETRIES
            answer.text = append_confirmation(answer.text, language, with_transfer=with_transfer)
            ac.patch(tenant_id, user_id, status="awaiting_confirmation",
                     retry_count=retry_count)
            save_turn(tenant_id, user_id, language, message, answer.text)
            touch_session(tenant_id, user_id)
            update_rolling_summary_async(tenant_id, user_id, language, message, answer.text)
            trace.set_answer(text=answer.text, grounding_score=answer.grounding_score, was_escalated=False)
            trace.flush()
            return MessageResult(
                answer=answer.text, image_urls=answer.image_urls, was_escalated=False,
            )

        # Non-troubleshooting (e.g. FAQ low-confidence "ยังไม่ได้") still escalates.
        _logger.info(
            f"[orchestrator] TRIGGER_HANDOFF non-troubleshooting → run_handoff_summary "
            f"(retry={retry_count})"
        )
        answer_text = run_handoff_summary(tenant_id, user_id, active_ctx, language)
        save_turn(tenant_id, user_id, language, message, answer_text)
        touch_session(tenant_id, user_id)
        update_rolling_summary_async(tenant_id, user_id, language, message, answer_text)
        trace.flush()
        return MessageResult(answer=answer_text, was_escalated=True)

    # ── Route — call BEFORE applying pending image so router sees raw message ──
    # Pass raw pending_image as image_situation so LLM router has full context.
    intent_result = detect_intent(message, language)
    decision = decide_route(
        intent_result.intent, message, language, tenant_id,
        recent_history=redis_history,
        active_context=active_ctx_str,
        summary=summary,
        image_situation=resolution.pending_image,
    )

    _logger.info(
        f"[orchestrator] router → route={decision.route.value} "
        f"is_new={decision.is_new} conf={decision.confidence:.2f} reason={decision.reason!r}"
    )
    trace.is_new = decision.is_new

    # ── LLM-classified explicit handoff request — fires immediately ───────────
    # The router LLM understands semantic intent, so this catches every
    # paraphrase ("โอน", "ขอแอดมิน", "คุยกับคน", "transfer me to a human")
    # without a keyword list. The resolver's keyword path stays as a fast-path
    # for button clicks.
    if decision.template_key == "handoff_request":
        _logger.info("[orchestrator] LLM-classified handoff_request → escalating now")
        trace.set_route(route="Route.TROUBLESHOOTING", reason="llm:handoff_request",
                        label="handoff_request", is_new=decision.is_new)
        answer_text = run_handoff_summary(tenant_id, user_id, active_ctx, language)
        save_turn(tenant_id, user_id, language, message, answer_text)
        touch_session(tenant_id, user_id)
        update_rolling_summary_async(tenant_id, user_id, language, message, answer_text)
        trace.set_answer(text=answer_text, grounding_score=1.0, was_escalated=True)
        trace.flush()
        return MessageResult(answer=answer_text, was_escalated=True)

    # ── Pending image — apply or discard based on router is_new decision ───────
    image_situation = ""
    if resolution.pending_image and not message.startswith(IMAGE_CAPTION_PREFIX):
        if not decision.is_new:
            image_situation = resolution.pending_image
            user_reply = message
            message    = f"{IMAGE_CAPTION_PREFIX}{resolution.pending_image}\nคำถาม: {user_reply}"
            logging.getLogger("image_flow").info(
                f"[image-flow] COMBINED pending image with reply for {tenant_id}/{user_id} "
                f"| is_new=False | user_reply={user_reply!r}"
            )
        else:
            logging.getLogger("image_flow").info(
                f"[image-flow] DISCARDED stale pending image for {tenant_id}/{user_id} "
                f"| is_new=True (new topic)"
            )
        clear_pending_image(tenant_id, user_id)

    # ── Topic shift: LLM says new topic on an existing active context ──────────
    # BUT: if the user is still on the same troubleshooting sub_type, treat it
    # as a continuation — preserves retry_count so the recheck→handoff loop
    # actually counts upward. Without this, every paraphrase ("ยังเจออยู่",
    # "เจอยังไง") that the LLM marks is_new=True wipes the context and resets
    # retry_count to 0, making escalation unreachable.
    same_troubleshooting_topic = (
        decision.route == Route.TROUBLESHOOTING
        and active_ctx
        and active_ctx.get("intent") == "troubleshooting"
        and active_ctx.get("sub_type") == decision.template_key
    )
    if same_troubleshooting_topic and decision.is_new:
        _logger.info(
            f"[orchestrator] LLM said is_new=True but sub_type matches active_ctx "
            f"({decision.template_key!r}) — overriding to is_new=False to keep retry_count"
        )
        decision.is_new = False

    if decision.is_new and active_ctx and decision.route not in (Route.CHITCHAT, Route.MISSING_INFO):
        _logger.info(f"[orchestrator] is_new=True with active_ctx → clearing old context")
        ac.patch(tenant_id, user_id, status="stale")
        active_ctx = {}
        clear_context(tenant_id, user_id)

    stage_input = StageInput(
        message=message,
        enriched_query=resolution.enriched_query,
        pending_image=image_situation,
        active_context=active_ctx,
        language=language,
        tenant_id=tenant_id,
        user_id=user_id,
        emp_id=emp_id,
        access_token=access_token,
        history=redis_history,
        summary=summary,
    )

    # ── Path execution ─────────────────────────────────────────────────────────

    # Pinned-FAQ shortcut — fires whenever a troubleshooting_* label has a
    # registered article in _TROUBLESHOOTING_FAQ_TITLES, regardless of is_new
    # or active context. This guarantees the canonical article (text + image)
    # for these well-known scenarios; otherwise BGE/LLM can drift toward an
    # unrelated article on followups or polluted catalogs.
    pinned_title = _TROUBLESHOOTING_FAQ_TITLES.get(decision.template_key)
    if pinned_title and not image_situation:
        pinned = _find_article_by_title(tenant_id, language, pinned_title)
        if pinned:
            from pipeline.answer_generator import GeneratedAnswer
            _logger.info(
                f"[orchestrator] pinned label={decision.template_key!r} → {pinned_title!r} "
                f"(image={'yes' if pinned.image_urls else 'no'}, is_new={decision.is_new})"
            )
            trace.set_route(
                route=str(decision.route), reason=f"pinned:{decision.template_key}",
                label=decision.template_key, is_new=decision.is_new,
            )
            trace.set_retrieval(
                query_used=f"[pinned] {pinned_title}",
                collection=f"{tenant_id}_{language}",
                documents=[pinned],
            )
            answer_obj = GeneratedAnswer(
                text=pinned.answer,
                grounding_score=1.0,
                was_escalated=False,
                route_taken=str(decision.route),
                image_urls=pinned.image_urls,
            )
            save_faq_context(tenant_id, user_id, question=message,
                             retrieved_docs=[pinned.answer], answer=answer_obj.text)
            ac.save_faq_context(tenant_id, user_id, topic=decision.template_key,
                                remark=message, last_user_need=message)
            save_turn(tenant_id, user_id, language, message, answer_obj.text)
            touch_session(tenant_id, user_id)
            update_rolling_summary_async(tenant_id, user_id, language, message, answer_obj.text)
            trace.set_answer(text=answer_obj.text, grounding_score=1.0, was_escalated=False)
            trace.flush()
            return MessageResult(
                answer=answer_obj.text, image_urls=answer_obj.image_urls, was_escalated=False,
            )

    # LLM says this is a followup on the same active topic
    if not decision.is_new and decision.route not in (Route.CHITCHAT, Route.MISSING_INFO):
        active_intent = active_ctx.get("intent", "")
        go_troubleshooting = (
            decision.route == Route.TROUBLESHOOTING
            or (active_intent == "troubleshooting" and decision.confidence < 0.8)
        )
        if go_troubleshooting:
            # Every troubleshooting followup increments the retry counter.
            # We do NOT auto-escalate to handoff — the post-processing step below
            # will surface the explicit "ต้องการโอน" option once retry_count
            # reaches MAX_TROUBLESHOOTING_RETRIES, leaving the choice to the user.
            retry_count = active_ctx.get("retry_count", 0) + 1
            ac.patch(tenant_id, user_id, retry_count=retry_count)
            active_ctx["retry_count"] = retry_count
            _logger.info(f"[orchestrator] troubleshooting followup retry={retry_count}")
            answer = _run_troubleshooting_recheck(
                message, language, tenant_id, user_id, emp_id,
                active_ctx, decision, redis_history, summary, trace,
                access_token=access_token,
            )
            # Belt-and-suspenders: re-patch retry_count after the recheck save.
            ac.patch(tenant_id, user_id, retry_count=retry_count)
        else:
            answer = _run_faq_followup(
                message, language, tenant_id, user_id,
                active_ctx, decision, redis_history, summary, trace,
                image_situation=image_situation,
                enriched_query=resolution.enriched_query,
            )

    elif decision.route == Route.CHITCHAT:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key, is_new=decision.is_new)
        answer = generate_answer(
            message=message, context="", language=language,
            tenant_id=tenant_id, intent=intent_result.intent.value,
            history=redis_history, route=str(decision.route),
            template_key=decision.template_key,
        )

    elif decision.route == Route.MISSING_INFO:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key, is_new=decision.is_new)
        answer = generate_answer(
            message=message, context="", language=language,
            tenant_id=tenant_id, intent=intent_result.intent.value,
            history=redis_history, route=str(decision.route),
            template_key=decision.template_key,
        )

    elif decision.route == Route.TROUBLESHOOTING:
        label = decision.template_key  # e.g. "troubleshooting_withdrawal"
        if label in _FLOWS:
            answer = _run_troubleshooting_staged(stage_input, label, decision, trace)
        else:
            answer = _run_troubleshooting_new(
                message, language, tenant_id, user_id, emp_id,
                decision, redis_history, summary, trace,
                access_token=access_token,
            )

    else:
        answer = _run_faq(
            message, language, tenant_id, user_id,
            decision, redis_history, summary, trace,
            image_situation=image_situation,
        )

    # ── FAQ low-confidence confirmation ───────────────────────────────────────
    # Only fire when bot gave a REAL but uncertain answer (0.15 ≤ score < threshold).
    # score < 0.15 = pure fallback ("ไม่มีข้อมูล") — adding "ตอบโจทย์ไหม?" is nonsensical.
    threshold = _GLOBAL_CFG.get("confirmation", {}).get("faq_low_confidence_threshold", 0.4)
    if (
        decision.route == Route.FAQ
        and decision.is_new
        and 0.15 <= answer.grounding_score < threshold
        and not answer.was_escalated
    ):
        answer.text = append_confirmation(answer.text, language)
        ac.patch(tenant_id, user_id,
                 source="faq", intent="faq", status="awaiting_confirmation",
                 faq_context={
                     "last_query":  resolution.enriched_query,
                     "last_answer": answer.text,
                     "score":       answer.grounding_score,
                 },
                 handoff_reason="faq_low_confidence")
        _logger.info(f"[orchestrator] FAQ low confidence ({answer.grounding_score:.2f}) → appended confirmation")

    # ── Troubleshooting: always ask for confirmation after the diagnosis ──────
    # The recheck-before-handoff loop relies on status=awaiting_confirmation +
    # confirmation prompt so the user can say "ก็ยังไม่ได้" (→ resolver fires
    # TRIGGER_HANDOFF → recheck) or "ได้แล้ว" (→ resolver fires END_FLOW → resolved).
    # Without this, repeated "still not working" replies just re-classify as
    # the same troubleshooting query and return the same answer in a loop.
    if decision.route == Route.TROUBLESHOOTING and not answer.was_escalated:
        # After MAX retries, surface the explicit "ต้องการโอน" option so the
        # user can opt into handoff. Read the freshly-patched retry_count from
        # active_context (the followup branch above bumped it).
        latest_ctx = ac.load(tenant_id, user_id) or active_ctx
        retry_count = latest_ctx.get("retry_count", 0)
        with_transfer = retry_count >= MAX_TROUBLESHOOTING_RETRIES
        answer.text = append_confirmation(answer.text, language, with_transfer=with_transfer)
        ac.patch(tenant_id, user_id, status="awaiting_confirmation")
        _logger.info(
            f"[orchestrator] troubleshooting → appended confirmation "
            f"(retry={retry_count}, with_transfer={with_transfer})"
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
    access_token: str = "",
):
    from agent.planner import run_troubleshooting_agent
    recheck_emp_id  = (active_ctx or {}).get("employee_id") or emp_id
    recheck_subtype = (active_ctx or {}).get("sub_type") or decision.template_key

    trace.set_route(route="Route.TROUBLESHOOTING", reason=f"recheck: {decision.reason}", is_new=False)
    agent_result = run_troubleshooting_agent(
        employee_id=recheck_emp_id, issue=message, language=language,
        tenant_id=tenant_id, sub_type=recheck_subtype, access_token=access_token,
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
    access_token: str = "",
):
    from agent.planner import run_troubleshooting_agent
    trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key, is_new=decision.is_new)
    agent_result = run_troubleshooting_agent(
        employee_id=emp_id, issue=message, language=language,
        tenant_id=tenant_id, sub_type=decision.template_key, access_token=access_token,
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


def _run_troubleshooting_staged(
    si: StageInput,
    label: str,
    decision,
    trace,
):
    """
    Execute stage_order from troubleshooting_flows.yaml for a given flow label.
    Returns a GeneratedAnswer. Appends confirmation and saves awaiting_confirmation
    when the confirmation stage is reached.
    """
    flow_cfg   = _FLOWS[label]
    stage_order = flow_cfg.get("stage_order", [])
    stage_trace: list[dict] = []
    answer = None

    trace.set_route(route=str(Route.TROUBLESHOOTING), reason=f"staged:{label}", label=label)

    for stage in stage_order:

        if stage == "faq_first":
            faq_cfg   = flow_cfg["faq_first"]
            faq_answer = _run_faq(
                si.message, si.language, si.tenant_id, si.user_id,
                decision, si.history, si.summary, trace,
                image_situation=si.pending_image,
                query_override=si.enriched_query,
            )
            skip_threshold = faq_cfg.get("skip_confirmation_if_score_above", 0.75)
            stage_trace.append({
                "stage": "faq_first",
                "score": faq_answer.grounding_score,
                "result": "skip_confirmation" if faq_answer.grounding_score > skip_threshold else "confirmation_needed",
            })
            ac.patch(si.tenant_id, si.user_id,
                     source="troubleshooting", intent=label,
                     faq_context={
                         "last_query":  si.enriched_query,
                         "last_answer": faq_answer.text,
                         "score":       faq_answer.grounding_score,
                     })
            if faq_answer.grounding_score > skip_threshold:
                _logger.info(f"[staged:{label}] faq_first score={faq_answer.grounding_score:.2f} > {skip_threshold} → skip confirmation")
                return faq_answer
            answer = faq_answer

        elif stage == "api_check":
            answer = _run_troubleshooting_new(
                si.message, si.language, si.tenant_id, si.user_id, si.emp_id,
                decision, si.history, si.summary, trace,
                access_token=si.access_token,
            )
            stage_trace.append({"stage": "api_check", "root_cause": getattr(answer, "root_cause", "")})

        elif stage == "confirmation":
            if answer is None:
                break
            answer.text = append_confirmation(answer.text, si.language)
            ac.patch(si.tenant_id, si.user_id,
                     source="troubleshooting", intent=label,
                     status="awaiting_confirmation")
            stage_trace.append({"stage": "confirmation", "result": "waiting"})
            _logger.info(f"[staged:{label}] stage_trace={stage_trace}")
            return answer

    _logger.info(f"[staged:{label}] stage_trace={stage_trace}")
    return answer


def _run_faq_followup(
    message, language, tenant_id, user_id,
    active_ctx, decision, redis_history, summary, trace,
    image_situation: str = "",
    enriched_query: str = "",   # from context resolver — takes priority over search_query
):
    rag_query = enriched_query or decision.search_query or message
    if image_situation:
        rag_query = f"{rag_query} {image_situation}"
    trace.set_route(route=str(Route.FAQ), reason=f"faq_followup: {decision.reason}", is_new=False)
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

    if image_situation:
        context = _prepend_image_situation(context, image_situation, language)
        logging.getLogger("image_flow").info(
            f"[image-flow] APPLIED image situation to FAQ followup context "
            f"({len(image_situation)} chars)"
        )

    from pipeline.answer_generator import FOLLOWUP_SYSTEM_PROMPT
    base   = FOLLOWUP_SYSTEM_PROMPT.get(language, FOLLOWUP_SYSTEM_PROMPT["th"])
    system = _build_system_with_summary(base, summary)
    answer = generate_answer(
        message=message, context=context, language=language, tenant_id=tenant_id,
        intent="question", history=redis_history, route=str(Route.FAQ),
        top_retrieval_score=max(top_score, 0.45) if cached_faq else top_score,
        system_prompt_override=system,
    )
    if (
        result.documents and result.documents[0].image_urls
        and top_score >= 0.45 and not _is_fallback_answer(answer.text)
        and _answer_uses_doc(answer.text, result.documents[0].answer)
    ):
        answer.image_urls = result.documents[0].image_urls
    save_faq_context(tenant_id, user_id, question=message,
                     retrieved_docs=[d.answer for d in result.documents], answer=answer.text)
    ac.update_remark(tenant_id, user_id, message)
    return answer


_QUERY_REWRITE_SYSTEM = (
    "Rewrite the user's question as a short Thai search phrase for semantic search. "
    "Use exact FAQ article title vocabulary. Return the phrase only — no explanation."
)
# Troubleshooting recheck loop:
#   "ยังไม่ได้" attempt 1 → recheck #1
#   "ยังไม่ได้" attempt 2 → recheck #2
#   "ยังไม่ได้" attempt 3 → escalate to human (handoff summary)
MAX_TROUBLESHOOTING_RETRIES = 3

_REWRITE_SCORE_THRESHOLD   = 0.35
_LLM_RERANK_GRAY_LOW       = 0.55   # below this → top-3 are too weak to LLM-rerank;
                                    # go straight to full_scan over the whole catalog.
_LLM_RERANK_GRAY_HIGH      = 0.70   # above this → vector+BGE is confident enough.
                                    # Direct hits score ~0.72+; wrong-but-plausible
                                    # articles top out around 0.6-0.69.
_FULL_SCAN_TRIGGER_SCORE   = 0.55   # top_score < this → run full_scan as safety net.

# When the router emits one of these troubleshooting_* labels, route to FAQ but
# pin to a specific article (looked up by exact Question match in the tenant's
# Qdrant collection). Skips vector+BGE for known mappings — guaranteed to return
# the right text + image when the article exists.
_TROUBLESHOOTING_FAQ_TITLES: dict[str, str] = {
    "troubleshooting_signup":            "ลงทะเบียนด้วยรหัสพนักงานและเลขบัตรประชาชน",
    "troubleshooting_cant_find_company": "วิธีค้นหาบริษัทของคุณ",
    "troubleshooting_money_not_arrived": "ไม่ได้รับเงินที่เบิก",
    "troubleshooting_cant_receive_otp":  "ไม่ได้รับรหัส OTP",
}

_ARTICLE_SELECT_SYSTEM = (
    "You pick the FAQ article whose answer addresses what the user is asking about. "
    "Match by intent and meaning, not by surface vocabulary — read each candidate's "
    "answer text to decide. Words that refer to the same action or concept are matches "
    "even when spelled differently (synonyms, paraphrases, alternate verbs). "
    "An article counts as a match if its answer states or contains the fact or steps "
    "the user needs, regardless of how the question is worded. "
    "Reply with ONLY a single number: the candidate index (0, 1, 2, ...), "
    "or -1 if none of the candidates contain the answer. "
    "Do not explain. Do not add any other text."
)


def _lazy_rewrite_query(message: str, language: str) -> str:
    """LLM query rewrite — called only when first retrieval score < 0.35."""
    try:
        from llm.client import call_llm
        rewritten = call_llm(
            messages=[{"role": "user", "content": message}],
            system=_QUERY_REWRITE_SYSTEM,
            max_tokens=40,
            language=language,
            step="query_rewrite",
        )
        return rewritten.strip() if rewritten else message
    except Exception:
        return message


# Catalog cache: avoids hitting Qdrant scroll on every full_scan.
# Key: (tenant_id, language) → (timestamp, list_of_payloads)
_CATALOG_TTL_SECONDS = 300   # 5 min — refreshed automatically after reindex
_catalog_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def _load_catalog(tenant_id: str, language: str) -> list[dict]:
    """Pull every article payload for the tenant from Qdrant. Cached for 5 min."""
    key = (tenant_id, language)
    cached = _catalog_cache.get(key)
    if cached and time.time() - cached[0] < _CATALOG_TTL_SECONDS:
        return cached[1]

    from rag.retriever import _get_client, _get_collection_name
    try:
        client     = _get_client()
        collection = _get_collection_name(tenant_id, language)
        points, _  = client.scroll(
            collection_name=collection,
            limit=500,
            with_payload=True,
            with_vectors=False,
        )
        payloads = [p.payload or {} for p in points]
    except Exception as e:
        _logger.warning(f"[faq] catalog scroll failed for {tenant_id!r}: {e}")
        payloads = []

    _catalog_cache[key] = (time.time(), payloads)
    return payloads


def _find_article_by_title(tenant_id: str, language: str, title: str):
    """Look up a single article in the cached tenant catalog by exact Question match."""
    payloads = _load_catalog(tenant_id, language)
    for p in payloads:
        if p.get("question", "").strip() == title.strip():
            return _payload_to_doc(p, tenant_id, score=1.0)
    return None


def _payload_to_doc(payload: dict, tenant_id: str, score: float):
    """Convert a Qdrant payload dict into a RetrievedDocument."""
    from rag.retriever import RetrievedDocument
    tags_raw = payload.get("tags", "")
    fu_raw   = payload.get("followup_questions", "")
    img_raw  = payload.get("image_urls", "")
    return RetrievedDocument(
        question=payload.get("question", ""),
        answer=payload.get("answer", ""),
        context=payload.get("context", ""),
        source_type=payload.get("source_type", ""),
        company_id=payload.get("company_id", tenant_id),
        score=score,
        tags=[t.strip() for t in tags_raw.split(";") if t.strip()] if tags_raw else [],
        followup_questions=[f.strip() for f in fu_raw.split(";") if f.strip()] if fu_raw else [],
        incident=payload.get("incident", ""),
        image_urls=[u.strip() for u in img_raw.split(";") if u.strip()] if img_raw else [],
    )


def _bge_full_scan(message: str, tenant_id: str, language: str):
    """
    Last-resort fallback when vector search + BGE-on-top-25 missed the right article.

    Two-stage: BGE narrows to top-5 over the FULL tenant catalog (~300ms),
    then LLM picks the best of those 5 — or -1 if none match (~500ms).
    BGE alone can't bridge semantic gaps (e.g. "เบิกได้กี่ครั้ง" vs
    "เงื่อนไขการเบิก": right article often ranks #2 by 0.03–0.07).
    """
    from rag.reranker import rerank

    payloads = _load_catalog(tenant_id, language)
    if not payloads:
        return None

    doc_texts = [f"{p.get('question','')} {p.get('answer','')}" for p in payloads]

    # Stage 1: BGE → top 5 candidates (no threshold; the LLM is the gate)
    reranked = rerank(query=message, documents=doc_texts, top_k=5, threshold=0.0)
    if not reranked:
        return None

    candidates = [_payload_to_doc(payloads[r.index], tenant_id, r.score) for r in reranked]

    # Stage 2: LLM picks the right one or rejects all
    pick = _llm_select_article(message, candidates, language)
    if pick == -1:
        _logger.info(f"[faq] full_scan: BGE top-5 found, LLM rejected all → no match")
        return None

    chosen = candidates[pick]
    _logger.info(
        f"[faq] full_scan: bge_rank={pick+1} bge_score={chosen.score:.2f} "
        f"→ {chosen.question[:60]!r}"
    )
    return chosen


# Fast picker model — separate from the main LLM. Override via FAST_PICKER_MODEL env var.
# Defaults: Gemini Flash-Lite (no thinking budget) → ~500ms vs ~2.5s for Flash thinking.
@lru_cache(maxsize=1)
def _get_fast_picker():
    provider_name = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    override      = os.environ.get("FAST_PICKER_MODEL", "")
    if provider_name == "google":
        from llm.providers.google import GoogleProvider
        return GoogleProvider(model=override or "gemini-2.5-flash-lite")
    if provider_name == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=override or "claude-haiku-4-5-20251001")
    # openai or other → fall back to default provider
    from llm.client import get_provider
    return get_provider()


def _llm_select_article(message: str, candidates: list, language: str) -> int:
    """
    LLM acts as a smart reranker when vector+BGE scores are ambiguous.
    Returns the candidate index that best answers `message`, or -1 if none match.
    Uses the fast picker model (Flash-Lite / Haiku) — no thinking, ~500ms.
    """
    if not candidates:
        return -1
    catalog_lines = []
    for i, c in enumerate(candidates):
        # Show enough answer for the LLM to judge by content, not just by title.
        ans = (c.answer or "").replace("\n", " ")[:400]
        catalog_lines.append(f"[{i}] Q: {c.question}\n    A: {ans}")
    prompt = (
        f"User question: {message}\n\n"
        f"Candidates:\n" + "\n".join(catalog_lines) +
        "\n\nWhich candidate answers the user's question? Reply with one number only."
    )
    try:
        import re
        provider = _get_fast_picker()
        t0       = time.perf_counter()
        response = provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system=_ARTICLE_SELECT_SYSTEM,
            max_tokens=16,   # response is just a small integer
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        # Record into the active pipeline trace so the step shows up in faq_trace.log
        try:
            from utils.pipeline_logger import record_llm_call
            record_llm_call(
                step="article_select",
                model=response.model or provider.get_model_name(),
                in_tokens=response.input_tokens,
                out_tokens=response.output_tokens,
                latency_ms=latency_ms,
                system=_ARTICLE_SELECT_SYSTEM,
                prompt=prompt,
                reply=response.text,
            )
        except Exception:
            pass
        m = re.search(r"-?\d+", response.text or "")
        if not m:
            return -1
        n = int(m.group())
        return n if -1 <= n < len(candidates) else -1
    except Exception as e:
        _logger.debug(f"[faq] llm_select_article failed: {e}")
        return -1


def _run_faq(
    message, language, tenant_id, user_id,
    decision, redis_history, summary, trace,
    image_situation: str = "",
    query_override: str = "",   # from staged or context resolver — takes priority
):
    cached_faq = load_faq_context(tenant_id, user_id)
    rag_query  = query_override or decision.search_query or message
    # Augment retrieval query with image keywords so we match fee/error/etc.
    # FAQs that the user's bare question wouldn't surface on its own.
    if image_situation:
        rag_query = f"{rag_query} {image_situation}"

    trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key, is_new=decision.is_new)

    # Direct-pass shortcut: troubleshooting_* labels routed to FAQ have a known
    # target article. Pin to that article (text + image verbatim) — fast and
    # deterministic for these well-known scenarios (signup, cant_find_company,
    # money_not_arrived, cant_receive_otp). Fires regardless of cached_faq
    # because the explicit label intent overrides any stale cache.
    # Skipped only when an image_situation is active (the LLM must combine
    # FAQ with the user's screen).
    pinned_title = _TROUBLESHOOTING_FAQ_TITLES.get(decision.template_key)
    if pinned_title and decision.is_new and not image_situation:
        pinned = _find_article_by_title(tenant_id, language, pinned_title)
        if pinned:
            from pipeline.answer_generator import GeneratedAnswer
            _logger.info(
                f"[faq] pinned label={decision.template_key!r} → {pinned_title!r} "
                f"(image={'yes' if pinned.image_urls else 'no'})"
            )
            trace.set_retrieval(
                query_used=f"[pinned] {pinned_title}",
                collection=f"{tenant_id}_{language}",
                documents=[pinned],
            )
            answer = GeneratedAnswer(
                text=pinned.answer,
                grounding_score=1.0,
                was_escalated=False,
                route_taken=str(decision.route),
                image_urls=pinned.image_urls,
            )
            save_faq_context(tenant_id, user_id, question=message,
                             retrieved_docs=[pinned.answer], answer=answer.text)
            ac.save_faq_context(tenant_id, user_id, topic=decision.template_key,
                                remark=message, last_user_need=message)
            return answer

    _t0 = time.perf_counter()
    result = retrieve(rag_query, tenant_id, language, top_k=3)
    trace.mark_step("retrieval", (time.perf_counter() - _t0) * 1000)

    top_score = result.documents[0].score if result.documents else 0.0

    # Lazy query rewrite: if first retrieval score is low and no override was given,
    # call LLM to rewrite the query using FAQ article vocabulary then retrieve again.
    if top_score < _REWRITE_SCORE_THRESHOLD and not query_override:
        rewritten = _lazy_rewrite_query(message, language)
        if rewritten != message:
            _logger.info(f"[faq] low score ({top_score:.2f}) → rewrite: {rewritten!r}")
            _t1 = time.perf_counter()
            result2 = retrieve(rewritten, tenant_id, language, top_k=3)
            trace.mark_step("retrieval_rewrite", (time.perf_counter() - _t1) * 1000)
            if result2.documents and result2.documents[0].score > top_score:
                result    = result2
                top_score = result2.documents[0].score
                rag_query = rewritten

    # LLM smart reranker fires in two cases:
    #  (a) Top score in gray zone (0.35–0.6): vector+BGE not confident.
    #  (b) Top score moderate (<0.7) AND #1 vs #2 gap < 0.05: BGE can't separate
    #      a wrong article from the right one (e.g. "เบิกได้กี่ครั้งต่อเดือน":
    #      "ติดตามสถานะ"=0.606 vs "เงื่อนไขการเบิก"=0.591 — only 0.015 apart).
    _rank2_for_rerank = result.documents[1].score if len(result.documents) > 1 else 0.0
    _gray_zone        = _LLM_RERANK_GRAY_LOW <= top_score < _LLM_RERANK_GRAY_HIGH
    _close_call       = top_score < 0.7 and (top_score - _rank2_for_rerank) < 0.05
    if (_gray_zone or _close_call) and len(result.documents) > 1 and not cached_faq:
        _t2 = time.perf_counter()
        pick = _llm_select_article(message, result.documents[:3], language)
        trace.mark_step("llm_rerank", (time.perf_counter() - _t2) * 1000)
        if pick == -1:
            # LLM picker rejected everything. Fast/cheap pickers (Flash-Lite,
            # Haiku) sometimes reject paraphrase matches that BGE found correctly
            # (e.g. "ถอนเงิน" vs "เบิกเงิน"). Only clear results when BGE itself
            # is also weak — otherwise trust BGE's top hit.
            if top_score >= 0.45:
                _logger.info(
                    f"[faq] llm_rerank: said -1 but BGE top is solid ({top_score:.2f}) "
                    f"→ trust BGE: {result.documents[0].question[:40]!r}"
                )
            else:
                _logger.info(f"[faq] llm_rerank: none of top-3 match (BGE weak {top_score:.2f}) → clear results")
                result.documents = []
                top_score        = 0.0
        elif pick > 0:
            chosen = result.documents[pick]
            rest   = [d for i, d in enumerate(result.documents) if i != pick]
            _logger.info(f"[faq] llm_rerank: promoted #{pick} → {chosen.question[:40]!r}")
            result.documents = [chosen] + rest
            top_score        = chosen.score

    # Safety net: weak top-3 → BGE-rescore against the entire tenant catalog (cached).
    # Fires when LLM rerank emptied the result OR top score is below the trigger
    # (top-3 candidates aren't strong enough to be trusted, even if rerank picked one).
    if (not result.documents or top_score < _FULL_SCAN_TRIGGER_SCORE) and not query_override and not cached_faq:
        _t3 = time.perf_counter()
        fallback_doc = _bge_full_scan(message, tenant_id, language)
        trace.mark_step("bge_full_scan", (time.perf_counter() - _t3) * 1000)
        if fallback_doc:
            result.documents = [fallback_doc]
            top_score        = fallback_doc.score
            rag_query        = f"[full_scan] {message}"

    q_label = f"[rewrite] {result.query_used}" if rag_query != message else result.query_used
    trace.set_retrieval(query_used=q_label, collection=result.collection, documents=result.documents)

    context   = build_context(result.documents, language)
    top_doc   = result.documents[0] if result.documents else None

    # High-confidence match: return the article answer + image verbatim.
    # Articles with images: the image IS the answer — always direct-pass, LLM must not be in the middle.
    # Text-only articles: require gap ≥ 0.05 vs rank #2 to avoid returning wrong article when two are close.
    # Image-situation present: skip direct-pass — the LLM must combine FAQ with the user's screen.
    _rank2_score = result.documents[1].score if len(result.documents) > 1 else 0.0
    _gap = top_score - _rank2_score
    _has_image = bool(top_doc and top_doc.image_urls)
    if (
        top_doc and top_score >= 0.45 and not cached_faq
        and not image_situation
        and (_has_image or _gap >= 0.05)
    ):
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

    if image_situation:
        context = _prepend_image_situation(context, image_situation, language)
        logging.getLogger("image_flow").info(
            f"[image-flow] APPLIED image situation to FAQ context "
            f"({len(image_situation)} chars, top_score={top_score:.3f})"
        )

    system = _build_system_with_summary(SYSTEM_PROMPT.get(language, SYSTEM_PROMPT["th"]), summary)
    answer = generate_answer(
        message=message, context=context, language=language, tenant_id=tenant_id,
        intent="question", history=redis_history, route=str(decision.route),
        top_retrieval_score=top_score, system_prompt_override=system,
    )
    # Fallback text ("ไม่มีข้อมูลในส่วนนี้" / "ไม่พบข้อมูล") must never trigger an
    # image or be persisted as context: grounding_score is unreliable (1.0 when fallback
    # recycles from a poisoned [Previous answer]), so check the text directly.
    # Also skip image when the LLM generated a novel answer that doesn't use the
    # top doc's content (e.g. "ขอลิงค์ android" → LLM writes a download answer that
    # doesn't actually come from the wrong-but-retrieved top doc).
    if (
        top_doc and top_doc.image_urls and top_score >= 0.45
        and not _is_fallback_answer(answer.text)
        and _answer_uses_doc(answer.text, top_doc.answer)
    ):
        answer.image_urls = top_doc.image_urls
    if not _is_fallback_answer(answer.text):
        save_faq_context(tenant_id, user_id, question=message,
                         retrieved_docs=[d.answer for d in result.documents], answer=answer.text)
        ac.save_faq_context(tenant_id, user_id, topic=message[:60],
                            remark=message, last_user_need=message)
    return answer
