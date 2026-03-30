"""
Entry point for CS Chatbot Agent.

Usage:
    python main.py api      # Start FastAPI LINE webhook server
    python main.py gradio   # Start Gradio test UI
"""

import sys
import argparse


def run_api() -> None:
    """Start the FastAPI server for LINE webhook."""
    import uvicorn
    from interface.fastapi_app import app

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)


def run_gradio() -> None:
    """Start the Gradio test UI."""
    from interface.gradio_app import demo

    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="CS Chatbot Agent")
    parser.add_argument(
        "mode",
        choices=["api", "gradio"],
        help="Run mode: 'api' for LINE webhook, 'gradio' for test UI",
    )
    args = parser.parse_args()

    if args.mode == "api":
        run_api()
    elif args.mode == "gradio":
        run_gradio()


if __name__ == "__main__":
    main()
