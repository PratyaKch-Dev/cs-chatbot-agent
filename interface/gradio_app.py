"""
Gradio test UI — local development and QA testing.

Simulates a LINE chat conversation without needing a real LINE account.
"""

import logging
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from pipeline.orchestrator import handle_message
import memory.active_context as ac
from memory.history import clear_history
from memory.context_cache import clear_context
from memory.session import end_session
from memory.summarizer import clear_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

TENANT_ID   = "happy_nest_space"
EMPLOYEE_ID = "EMP001"   # default for troubleshooting tests


def _chat(
    message: str,
    history: list[list[str]],
    tenant_id: str,
    employee_id: str,
) -> tuple[str, str]:
    """Returns (answer_text, trace_text). History list is display-only; Redis owns state."""
    if not message.strip():
        return "", ""
    result = handle_message(
        tenant_id=tenant_id,
        user_id=employee_id,
        message=message,
        employee_id=employee_id,
    )
    answer = result.answer
    if result.image_urls and not result.was_escalated:
        imgs = "\n".join(f"![]({url})" for url in result.image_urls)
        answer = f"{answer}\n\n{imgs}"
    return answer, _read_last_trace()


_LOG_FILE = Path(__file__).parent.parent / "logs" / "faq_trace.log"
_SEP = "─" * 72


def _read_last_trace() -> str:
    """Return the last trace block from faq_trace.log."""
    if not _LOG_FILE.exists():
        return "(no log yet)"
    text = _LOG_FILE.read_text(encoding="utf-8")
    parts = text.split(_SEP)
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

        chatbot   = gr.Chatbot(label="Conversation", height=500, render_markdown=True)
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

        def respond(message, history, tenant_id, employee_id):
            if not message.strip():
                return history, "", ""
            reply, trace = _chat(message, history, tenant_id, employee_id)
            history.append([message, reply])
            return history, "", trace

        def clear_all(tenant_id, employee_id):
            for lang in ("th", "en"):
                clear_history(tenant_id, employee_id, lang)
                clear_summary(tenant_id, employee_id, lang)
            clear_context(tenant_id, employee_id)
            ac.clear(tenant_id, employee_id)
            end_session(tenant_id, employee_id)
            return [], "", ""

        send_btn.click(
            respond,
            inputs=[msg_input, chatbot, tenant_input, emp_input],
            outputs=[chatbot, msg_input, trace_box],
        )
        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot, tenant_input, emp_input],
            outputs=[chatbot, msg_input, trace_box],
        )
        clear_btn.click(
            clear_all,
            inputs=[tenant_input, emp_input],
            outputs=[chatbot, msg_input, trace_box],
        )

    return demo


demo = build_demo()
