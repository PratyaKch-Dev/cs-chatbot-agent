"""
Gradio test UI — local development and QA testing.

Simulates a LINE chat conversation without needing a real LINE account.
Multi-message combining is handled by pipeline.combiner, not here.
"""

import logging
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from pipeline.orchestrator import handle_message
from pipeline.combiner import push, claim, is_current, complete, reset
from llm.vision import describe_image
from llm.templates import IMAGE_CAPTION_PREFIX
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
_logger = logging.getLogger("gradio_app")

TENANT_ID   = "happy_nest_space"
EMPLOYEE_ID = "EMP001"

# Module-level committed state — avoids Gradio state propagation race conditions
# when two process_messages calls are queued back-to-back.
_committed_store: dict[str, list] = {}

_LOG_FILE = Path(__file__).parent.parent / "logs" / "faq_trace.log"
_SEP = "─" * 72


def _read_last_trace() -> str:
    if not _LOG_FILE.exists():
        return "(no log yet)"
    text = _LOG_FILE.read_text(encoding="utf-8")
    parts = text.split(_SEP)
    blocks = []
    i = 1
    while i + 1 < len(parts):
        blocks.append((_SEP + parts[i] + _SEP + parts[i + 1]).strip())
        i += 2
    return blocks[-1] if blocks else "(empty log)"


def _call_pipeline(message: str, tenant_id: str, employee_id: str) -> tuple[str, str]:
    result = handle_message(
        tenant_id=tenant_id,
        user_id=employee_id,
        message=message,
        employee_id=employee_id,
    )
    answer = result.answer
    if result.image_urls and not result.was_escalated:
        answer += "\n\n" + "\n".join(f"![]({u})" for u in result.image_urls)
    return answer, _read_last_trace()


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="CS Chatbot — Test UI", theme=gr.themes.Soft()) as demo:
        gr.Markdown("## CS Chatbot Agent — Test UI")
        gr.Markdown(
            "**FAQ:** ask any general question.  \n"
            "**Troubleshooting:** use keywords like `เบิกไม่ได้` / `ยอด 0` — set Employee ID below.  \n"
            "**Multi-message:** type quickly — if Q2 arrives while Q1 is processing, they combine into one answer."
        )

        with gr.Row():
            tenant_input = gr.Textbox(value=TENANT_ID,   label="Tenant ID",   scale=1)
            emp_input    = gr.Textbox(value=EMPLOYEE_ID, label="Employee ID (for troubleshooting)", scale=1)

        chatbot          = gr.Chatbot(label="Conversation", height=500, render_markdown=True)
        committed_state  = gr.State([])   # completed [user, bot] turns — source of truth for history
        msg_input = gr.Textbox(
            placeholder="พิมพ์ข้อความ / Type a message...",
            label="Message",
            scale=4,
        )
        img_input = gr.Image(type="filepath", label="ส่งรูปภาพ / Send image (optional)", scale=1)

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

        def enqueue_msg(message, image_path, chatbot_state, committed, tenant_id, employee_id):
            """Phase 1: instantly add message/image to queue and clear inputs."""
            has_text  = bool(message and message.strip())
            has_image = bool(image_path)
            if not has_text and not has_image:
                return chatbot_state, "", None, committed

            new_turns = []
            if has_image:
                img_bytes   = Path(image_path).read_bytes()
                suffix      = Path(image_path).suffix.lower()
                media_type  = "image/png" if suffix == ".png" else "image/jpeg"
                description = describe_image(img_bytes, media_type)

                if has_text:
                    # Combine into one message so the pipeline sees image as context for the question
                    combined = f"{IMAGE_CAPTION_PREFIX}{description}\nคำถาม: {message.strip()}"
                    push(tenant_id, employee_id, combined)
                    new_turns.append([f"🖼️ {message.strip()}", ""])
                else:
                    push(tenant_id, employee_id, IMAGE_CAPTION_PREFIX + description)
                    new_turns.append(["🖼️ (image)", ""])
            elif has_text:
                push(tenant_id, employee_id, message.strip())
                new_turns.append([message.strip(), ""])

            return chatbot_state + new_turns, "", None, committed

        def process_messages(committed, tenant_id, employee_id):
            """
            Phase 2: claim pending batch, run pipeline, update chat.

            Uses a module-level committed store (not Gradio state) as the history
            base — Gradio can pass stale state to queued events, which would cause
            turns to overwrite each other when two sends arrive in quick succession.
            concurrency_limit=1 ensures serial execution.
            """
            store_key = f"{tenant_id}:{employee_id}"
            # Always read from the module-level store; fall back to Gradio state
            # only on the very first call before anything has been stored.
            current = _committed_store.get(store_key, committed)

            for _ in range(5):  # max 5 combine iterations to avoid infinite loop
                gen, messages = claim(tenant_id, employee_id)
                _logger.info(f"[process_messages] gen={gen} messages={messages} committed_len={len(current)}")
                if gen is None or not messages:
                    return gr.update(), "", current

                combined = "\n".join(messages)
                reply, trace = _call_pipeline(combined, tenant_id, employee_id)

                if not is_current(tenant_id, employee_id, gen):
                    _logger.info(f"[process_messages] gen={gen} NOT current — combining with pending and retrying")
                    continue

                complete(tenant_id, employee_id)
                # Show each user bubble separately; bot reply only under the last one.
                new_turns = [[msg, None] for msg in messages[:-1]] + [[messages[-1], reply]]
                final = current + new_turns
                _committed_store[store_key] = final
                _logger.info(f"[process_messages] gen={gen} done — final turns={len(final)}")
                return final, trace, final

            # Safety: clear inflight so state doesn't get stuck
            complete(tenant_id, employee_id)
            return gr.update(), "", current

        def clear_all(tenant_id, employee_id):
            reset(tenant_id, employee_id)
            _committed_store.pop(f"{tenant_id}:{employee_id}", None)
            for lang in ("th", "en"):
                clear_history(tenant_id, employee_id, lang)
                clear_summary(tenant_id, employee_id, lang)
            clear_context(tenant_id, employee_id)
            ac.clear(tenant_id, employee_id)
            end_session(tenant_id, employee_id)
            return [], "", None, "", []

        _enqueue_inputs  = [msg_input, img_input, chatbot, committed_state, tenant_input, emp_input]
        _enqueue_outputs = [chatbot, msg_input, img_input, committed_state]
        _process_inputs  = [committed_state, tenant_input, emp_input]
        _process_outputs = [chatbot, trace_box, committed_state]

        send_btn.click(
            enqueue_msg,
            inputs=_enqueue_inputs,
            outputs=_enqueue_outputs,
        ).then(
            process_messages,
            inputs=_process_inputs,
            outputs=_process_outputs,
            concurrency_limit=1,
        )
        msg_input.submit(
            enqueue_msg,
            inputs=_enqueue_inputs,
            outputs=_enqueue_outputs,
        ).then(
            process_messages,
            inputs=_process_inputs,
            outputs=_process_outputs,
            concurrency_limit=1,
        )
        clear_btn.click(
            clear_all,
            inputs=[tenant_input, emp_input],
            outputs=[chatbot, msg_input, img_input, trace_box, committed_state],
        )

    return demo


demo = build_demo()
