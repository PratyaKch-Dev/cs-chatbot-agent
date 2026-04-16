"""
Troubleshooting agent batch tester.

Runs test scenarios through the full pipeline and prints a summary table.
Results are also written to logs/faq_trace.log as usual.

Usage:
    PYTHONPATH=. python scripts/test_troubleshooting.py
    USE_MOCK_APIS=true PYTHONPATH=. python scripts/test_troubleshooting.py
"""

import os
import argparse

from dotenv import load_dotenv
load_dotenv()

from utils.language import detect_language
from utils.pipeline_logger import PipelineTrace
from pipeline.router import decide_route, Route
from pipeline.answer_generator import generate_answer
from agent.planner import run_troubleshooting_agent

# (employee_id, issue, expected_root_cause)
TEST_SCENARIOS = [
    # ── Zero balance / can't withdraw ────────────────────────────────────────
    ("EMP004", "ยอด 0 บาท เบิกเงินไม่ได้",           "sync_pending"),
    ("EMP004", "แสดงผล 0 ทำไม",                       "sync_pending"),
    ("EMP004", "ยอดไม่ขึ้นเลยครับ",                  "sync_pending"),
    # ── Account issues ───────────────────────────────────────────────────────
    ("EMP005", "เบิกไม่ได้ครับ",                       "blacklisted"),
    ("EMP005", "เงินไม่ขึ้น บัญชีมีปัญหา",             "blacklisted"),
    ("EMP002", "ทำไมเบิกเงินไม่ได้",                  "status_inactive"),
    # ── Attendance anomalies (missed punches) ───────────────────────────────
    ("EMP003", "เบิกเงินไม่ได้เลย",                   "ok"),
    ("EMP003", "ทำไมเช็คอินไม่ขึ้น",                  "ok"),
    # ── Low balance — paycycle just started ──────────────────────────────────
    ("EMP006", "ทำไมเบิกเงินไม่ได้",                  "ok"),
    ("EMP006", "ยอดเงินเป็น 0 ครับ",                   "ok"),
    # ── Normal user (no blocking issue) ─────────────────────────────────────
    ("EMP001", "ทำไมยอดไม่อัปเดต",                    "ok"),
    ("EMP001", "หักเงินเท่าไหร่",                      "ok"),
]

SECTIONS = {
    0: "ยอด 0 / เบิกไม่ได้ (sync pending)",
    3: "ปัญหาบัญชี (blacklisted / suspended)",
    6: "ปัญหา punch in/out (attendance anomalies)",
    8: "ยอดต่ำ — paycycle เพิ่งเริ่ม (EMP006)",
    10: "ผู้ใช้ปกติ (ไม่มีปัญหา)",
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

COL_EMP  = 8
COL_Q    = 34
COL_ROOT = 14
COL_A    = 50


def run(tenant_id: str) -> None:
    print(f"\nTenant: {tenant_id}  Scenarios: {len(TEST_SCENARIOS)}\n")
    print(f"{'#':<4} {'Emp':<{COL_EMP}} {'Issue':<{COL_Q}} {'Root cause':<{COL_ROOT}} {'Pass?':<6} Answer preview")
    print("─" * 130)

    passed = failed = 0

    for i, (emp_id, issue, expected) in enumerate(TEST_SCENARIOS):
        if i in SECTIONS:
            print(f"\n  ── {SECTIONS[i]} ──")

        lang  = detect_language(issue)
        trace = PipelineTrace(tenant_id=tenant_id, query=issue, language=lang)

        decision = decide_route("question", issue, lang, tenant_id)
        trace.set_route(str(decision.route), decision.reason)

        agent_result = run_troubleshooting_agent(emp_id, issue, lang, tenant_id)
        trace.set_troubleshooting(
            employee_id=emp_id,
            root_cause=agent_result["root_cause"],
            tools_used=agent_result["tools_used"],
        )

        system  = TROUBLESHOOTING_SYSTEM_PROMPT.get(lang, TROUBLESHOOTING_SYSTEM_PROMPT["th"])
        answer  = generate_answer(
            message=issue,
            context=agent_result["diagnostic_context"],
            language=lang,
            tenant_id=tenant_id,
            intent="question",
            history=[],
            route=str(decision.route),
            system_prompt_override=system,
            prefilled_answer=agent_result.get("template_answer", ""),
        )
        trace.set_answer(answer.text, answer.grounding_score, answer.was_escalated)
        trace.flush()

        actual  = agent_result["root_cause"]
        correct = actual == expected
        mark    = "✅" if correct else "❌"
        if correct:
            passed += 1
        else:
            failed += 1

        preview  = answer.text.replace("\n", " ")[:COL_A]
        emp_col  = emp_id[:COL_EMP]
        q_col    = issue[:COL_Q]
        root_col = actual[:COL_ROOT]

        print(f"{i+1:<4} {emp_col:<{COL_EMP}} {q_col:<{COL_Q}} {root_col:<{COL_ROOT}} {mark:<6} {preview}")

    print("\n" + "─" * 130)
    print(f"  Total: {len(TEST_SCENARIOS)}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"  Accuracy: {passed / len(TEST_SCENARIOS) * 100:.0f}%")
    print()
    print("  Full traces written to logs/faq_trace.log")


if __name__ == "__main__":
    os.environ.setdefault("USE_MOCK_APIS", "true")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="hns")
    args = parser.parse_args()
    run(args.tenant)
