"""
Gradio test UI — local development and QA testing.

Simulates a LINE chat conversation without needing a real LINE account.
"""

from typing import Generator

import gradio as gr

# TODO Phase 3: import orchestrator
# from pipeline.orchestrator import handle_message

TENANT_ID = "hns"  # default tenant for testing


def _chat(message: str, history: list[list[str]], user_id: str) -> str:
    """Process a chat message and return a reply.

    TODO Phase 3: wire to pipeline orchestrator.
    """
    # Placeholder until orchestrator is implemented
    return f"[stub] received: {message}"


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="CS Chatbot — Test UI", theme=gr.themes.Soft()) as demo:
        gr.Markdown("## CS Chatbot Agent — Test UI")
        gr.Markdown("Simulates a LINE chat. Use any user ID to test multi-user sessions.")

        with gr.Row():
            user_id_input = gr.Textbox(
                value="test_user_001",
                label="User ID (simulates LINE user_id)",
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
