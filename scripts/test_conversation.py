"""
Simulate a multi-turn conversation exactly like Gradio does.

Usage:
    PYTHONPATH=. python scripts/test_conversation.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from interface.gradio_app import _chat

TENANT_ID   = "hns"
EMPLOYEE_ID = "EMP001"

CONVERSATION = [
    "สวัสดีครับ",
    "มีลิงค์ให้ดาวน์โหลดมั้ย",
    "ผมใช้ android ครับ",      # ← the follow-up that was broken before
]

SEP = "─" * 60


def run():
    history = []
    print(f"\n{'='*60}")
    print("  CONVERSATION TEST — follow-up context handling")
    print(f"{'='*60}\n")

    for turn, message in enumerate(CONVERSATION, 1):
        print(f"{SEP}")
        print(f"  Turn {turn}  USER: {message}")
        print(SEP)

        answer, trace = _chat(message, history, TENANT_ID, EMPLOYEE_ID)
        history.append([message, answer])

        print(f"  BOT: {answer}\n")

        # Pull just the route + retrieval lines from trace for quick read
        for line in trace.splitlines():
            stripped = line.strip()
            if any(stripped.startswith(tag) for tag in (
                "[2 ROUTER]", "[3 RETRIEVAL]", "[5 RESULT]",
                "label", "collection", "cleaned", "#1", "#2",
                "grounding", "escalated",
            )):
                print(f"  {stripped}")
        print()

    print(f"\n{'='*60}")
    print("  Done. Full trace → logs/faq_trace.log")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
