"""
Gradio test UI — local development and QA testing.

Simulates a LINE chat conversation without needing a real LINE account.
"""

import logging
import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from pipeline.router import decide_route, Route
from rag.retriever import retrieve, build_context
from pipeline.answer_generator import generate_answer
from utils.language import detect_language
from utils.pipeline_logger import PipelineTrace
from llm.intent import detect_intent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

TENANT_ID   = "hns"
EMPLOYEE_ID = "EMP001"   # default for troubleshooting tests

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


# Keywords that signal a follow-up question about specific diagnostic topics.
# When the user has an active diagnostic context, these route back through it
# instead of going to FAQ — so the LLM can answer with the employee's real data.
_FOLLOWUP_KEYWORDS = {
    "th": [
        "ซิงค์", "sync", "ล่าสุด", "ครั้งล่าสุด",
        "หักเงิน", "หัก", "ค่าปรับ", "ค่า",
        "ขาดงาน", "มาสาย", "สาย", "เข้างาน", "เช็คอิน",
        "กะ", "กะงาน", "เวลาทำงาน",
        "สถานะ", "บัญชี", "รายละเอียด",
    ],
    "en": [
        "sync", "last sync", "deduction", "absent", "late",
        "check in", "check out", "shift", "status", "detail",
    ],
}


def _is_followup(message: str, language: str) -> bool:
    msg_lower = message.lower()
    lang_key  = "th" if language == "th" else "en"
    return any(kw in msg_lower for kw in _FOLLOWUP_KEYWORDS.get(lang_key, []))


def _chat(
    message: str,
    history: list[list[str]],
    tenant_id: str,
    employee_id: str,
    diag_state: dict,
) -> tuple[str, str, dict]:
    """
    Returns (answer_text, trace_text, updated_diag_state).

    diag_state = {"diag_context": str, "emp_id": str}
    Cached after a troubleshooting run so follow-up questions can reference
    the same diagnostic data without re-running the agent.
    """
    if not message.strip():
        return "", "", diag_state

    language = detect_language(message)
    trace    = PipelineTrace(tenant_id=tenant_id, query=message, language=language)

    llm_history = []
    for user_msg, bot_msg in history:
        llm_history.append({"role": "user", "content": user_msg})
        llm_history.append({"role": "assistant", "content": bot_msg})

    intent_result = detect_intent(message, language)
    decision = decide_route(intent_result.intent, message, language, tenant_id)

    # If we have a cached diagnostic context AND the question looks like a follow-up,
    # answer using the cached context directly — no need to re-run the agent.
    cached_context = diag_state.get("diag_context", "")
    use_cached = (
        cached_context
        and diag_state.get("emp_id") == employee_id
        and _is_followup(message, language)
        and decision.route != Route.TROUBLESHOOTING  # new blocking issue takes priority
    )

    if use_cached:
        trace.set_route(route="Route.TROUBLESHOOTING", reason="follow-up: reusing cached diagnostic context")
        trace.set_troubleshooting(
            employee_id=employee_id,
            root_cause="follow_up",
            tools_used=[],
        )
        context = cached_context
        system  = TROUBLESHOOTING_SYSTEM_PROMPT.get(language, TROUBLESHOOTING_SYSTEM_PROMPT["th"])
        answer  = generate_answer(
            message=message,
            context=context,
            language=language,
            tenant_id=tenant_id,
            intent="question",
            history=llm_history,
            route="Route.TROUBLESHOOTING",
            system_prompt_override=system,
        )

    # ── Chitchat path ──────────────────────────────────────────────────────────
    elif decision.route == Route.CHITCHAT:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
        answer = generate_answer(
            message=message,
            context="",
            language=language,
            tenant_id=tenant_id,
            intent=intent_result.intent.value,
            history=llm_history,
            route=str(decision.route),
            template_key=decision.template_key,
        )

    # ── Missing info path ──────────────────────────────────────────────────────
    elif decision.route == Route.MISSING_INFO:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
        answer = generate_answer(
            message=message,
            context="",
            language=language,
            tenant_id=tenant_id,
            intent=intent_result.intent.value,
            history=llm_history,
            route=str(decision.route),
            template_key=decision.template_key,
        )

    # ── Troubleshooting path ───────────────────────────────────────────────────
    elif decision.route == Route.TROUBLESHOOTING:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
        from agent.planner import run_troubleshooting_agent
        agent_result = run_troubleshooting_agent(
            employee_id=employee_id,
            issue=message,
            language=language,
            tenant_id=tenant_id,
            sub_type=decision.template_key,
        )
        trace.set_troubleshooting(
            employee_id=employee_id,
            root_cause=agent_result["root_cause"],
            tools_used=agent_result["tools_used"],
        )
        context  = agent_result["diagnostic_context"]
        diag_state = {"diag_context": context, "emp_id": employee_id}
        system   = TROUBLESHOOTING_SYSTEM_PROMPT.get(language, TROUBLESHOOTING_SYSTEM_PROMPT["th"])
        answer   = generate_answer(
            message=message,
            context=context,
            language=language,
            tenant_id=tenant_id,
            intent="question",
            history=llm_history,
            route=str(decision.route),
            system_prompt_override=system,
            prefilled_answer=agent_result.get("template_answer", ""),
        )

    # ── FAQ path ───────────────────────────────────────────────────────────────
    else:
        trace.set_route(route=str(decision.route), reason=decision.reason, label=decision.template_key)
        result = retrieve(message, tenant_id, language, top_k=3)
        trace.set_retrieval(
            query_used=result.query_used,
            collection=result.collection,
            documents=result.documents,
        )
        context = build_context(result.documents, language)
        top_score = result.documents[0].score if result.documents else 0.0
        answer  = generate_answer(
            message=message,
            context=context,
            language=language,
            tenant_id=tenant_id,
            intent="question",
            history=llm_history,
            route=str(decision.route),
            top_retrieval_score=top_score,
        )

    trace.set_answer(
        text=answer.text,
        grounding_score=answer.grounding_score,
        was_escalated=answer.was_escalated,
    )
    trace.flush()
    return answer.text, _read_last_trace(), diag_state


_LOG_FILE = Path(__file__).parent.parent / "logs" / "faq_trace.log"
_SEP = "─" * 72


def _read_last_trace() -> str:
    """Return the last trace block from faq_trace.log."""
    if not _LOG_FILE.exists():
        return "(no log yet)"
    text = _LOG_FILE.read_text(encoding="utf-8")
    # Split on separator lines and grab the last complete block
    parts = text.split(_SEP)
    # parts: [..., header, body, header, body, ...]
    # Each block = SEP + header + SEP + body → indices come in pairs
    # Walk backwards to find last complete block (header + body between two SEPs)
    blocks = []
    i = 1
    while i + 1 < len(parts):
        block = _SEP + parts[i] + _SEP + parts[i + 1]
        blocks.append(block.strip())
        i += 2
    return blocks[-1] if blocks else "(empty log)"


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="CS Chatbot — Test UI", theme=gr.themes.Soft()) as demo:
        gr.Markdown("## CS Chatbot Agent — Test UI")
        gr.Markdown(
            "**FAQ:** ask any general question.  \n"
            "**Troubleshooting:** use keywords like `เบิกไม่ได้` / `ยอด 0` — set Employee ID below."
        )

        with gr.Row():
            tenant_input = gr.Textbox(value=TENANT_ID,   label="Tenant ID",   scale=1)
            emp_input    = gr.Textbox(value=EMPLOYEE_ID, label="Employee ID (for troubleshooting)", scale=1)

        chatbot   = gr.Chatbot(label="Conversation", height=500)
        msg_input = gr.Textbox(
            placeholder="พิมพ์ข้อความ / Type a message...",
            label="Message",
            scale=4,
        )

        with gr.Row():
            send_btn  = gr.Button("Send", variant="primary")
            clear_btn = gr.Button("Clear")

        with gr.Accordion("Pipeline trace (last request)", open=False):
            trace_box = gr.Code(
                label="faq_trace.log",
                language=None,
                interactive=False,
                lines=28,
            )

        # Persists the last diagnostic context so follow-up questions
        # (e.g. "ซิงค์ล่าสุดเมื่อไหร่", "หักเงินเท่าไหร่") can be answered
        # from the same employee data without re-running the agent.
        diag_state = gr.State({"diag_context": "", "emp_id": ""})

        def respond(message, history, tenant_id, employee_id, state):
            if not message.strip():
                return history, "", "", state
            reply, trace, new_state = _chat(message, history, tenant_id, employee_id, state)
            history.append([message, reply])
            return history, "", trace, new_state

        send_btn.click(
            respond,
            inputs=[msg_input, chatbot, tenant_input, emp_input, diag_state],
            outputs=[chatbot, msg_input, trace_box, diag_state],
        )
        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot, tenant_input, emp_input, diag_state],
            outputs=[chatbot, msg_input, trace_box, diag_state],
        )
        clear_btn.click(
            lambda: ([], "", "", {"diag_context": "", "emp_id": ""}),
            outputs=[chatbot, msg_input, trace_box, diag_state],
        )

    return demo


demo = build_demo()
