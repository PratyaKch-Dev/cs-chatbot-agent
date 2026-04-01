"""
Gradio test UI — local development and QA testing.

Simulates a LINE chat conversation without needing a real LINE account.
"""

import logging

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from pipeline.router import decide_route
from rag.retriever import retrieve, build_context
from pipeline.answer_generator import generate_answer
from utils.language import detect_language
from utils.pipeline_logger import PipelineTrace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

TENANT_ID = "hns"  # default tenant for testing


def _chat(message: str, history: list[list[str]], tenant_id: str) -> str:
    """Process a chat message through the FAQ pipeline."""
    if not message.strip():
        return ""

    language = detect_language(message)
    trace = PipelineTrace(tenant_id=tenant_id, query=message, language=language)

    # Build history in LLM format
    llm_history = []
    for user_msg, bot_msg in history:
        llm_history.append({"role": "user", "content": user_msg})
        llm_history.append({"role": "assistant", "content": bot_msg})

    decision = decide_route("question", message, language, tenant_id)
    trace.set_route(route=str(decision.route), reason=decision.reason)

    result = retrieve(message, tenant_id, language, top_k=3)
    trace.set_retrieval(
        query_used=result.query_used,
        collection=result.collection,
        documents=result.documents,
    )
    context = build_context(result.documents, language)

    answer = generate_answer(
        message=message,
        context=context,
        language=language,
        tenant_id=tenant_id,
        intent="question",
        history=llm_history,
        route=str(decision.route),
    )
    trace.set_answer(
        text=answer.text,
        grounding_score=answer.grounding_score,
        was_escalated=answer.was_escalated,
    )
    trace.flush()

    return answer.text


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="CS Chatbot — Test UI", theme=gr.themes.Soft()) as demo:
        gr.Markdown("## CS Chatbot Agent — Test UI")
        gr.Markdown("Simulates a LINE chat. Use any user ID to test multi-user sessions.")

        with gr.Row():
            user_id_input = gr.Textbox(
                value=TENANT_ID,
                label="Tenant ID",
                scale=1,
            )

        chatbot = gr.Chatbot(label="Conversation", height=500)
        msg_input = gr.Textbox(
            placeholder="พิมพ์ข้อความ / Type a message...",
            label="Message",
            scale=4,
        )

        with gr.Row():
            send_btn = gr.Button("Send", variant="primary")
            clear_btn = gr.Button("Clear")

        def respond(message: str, history: list, user_id: str):
            if not message.strip():
                return history, ""
            reply = _chat(message, history, user_id)
            history.append([message, reply])
            return history, ""

        send_btn.click(
            respond,
            inputs=[msg_input, chatbot, user_id_input],
            outputs=[chatbot, msg_input],
        )
        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot, user_id_input],
            outputs=[chatbot, msg_input],
        )
        clear_btn.click(lambda: ([], ""), outputs=[chatbot, msg_input])

    return demo


demo = build_demo()
