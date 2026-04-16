"""
Full pipeline tester — covers all four routes.

  CHITCHAT     — instant template, no LLM
  MISSING_INFO — instant template, no LLM
  FAQ          — retrieval + LLM answer
  TROUBLESHOOTING — agent diagnosis + answer

Usage:
    PYTHONPATH=. python scripts/test_all.py
    USE_MOCK_APIS=true PYTHONPATH=. python scripts/test_all.py
    USE_MOCK_APIS=true PYTHONPATH=. python scripts/test_all.py --tenant hns
"""

import os
import argparse

from dotenv import load_dotenv
load_dotenv()

from utils.language import detect_language
from utils.pipeline_logger import PipelineTrace
from pipeline.router import decide_route, Route
from pipeline.answer_generator import generate_answer
from llm.intent import detect_intent

TENANT_ID = "hns"

TROUBLESHOOTING_SYSTEM = {
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

# ── Test cases ─────────────────────────────────────────────────────────────────

CHITCHAT_CASES = [
    # (message, expected_route_label)
    ("สวัสดีครับ",              "greeting"),
    ("หวัดดีค่ะ",               "greeting"),
    ("hello",                    "greeting"),
    ("ขอบคุณมากนะคะ",           "thanks"),
    ("โอเคค่ะ เข้าใจแล้ว",     "thanks"),
    ("ok got it",                "thanks"),
    ("ลาก่อนนะครับ",            "goodbye"),
    ("bye",                      "goodbye"),
    ("ห่วยมากเลย",              "frustrated"),
    ("งงมากเลยค่ะ",             "confused"),
]

MISSING_INFO_CASES = [
    "ช่วยด้วยครับ",
    "มีปัญหาค่ะ",
    "?",
    "help",
]

FAQ_CASES = [
    # (question, lang, expect_escalated)
    ("เบิกเงินได้ตั้งแต่กี่โมงครับ",         "th", False),
    ("เบิกได้กี่ครั้งต่อเดือนคะ",            "th", False),
    ("เบิกได้สูงสุดเท่าไหร่",               "th", False),
    ("วันหยุดเสาร์อาทิตย์เบิกเงินได้ไหมคะ",  "th", False),
    ("เงินที่เบิกไปจะหักคืนตอนไหนครับ",      "th", False),
    ("มีดอกเบี้ยไหมถ้าเบิกเงินล่วงหน้า",     "th", False),
    ("โหลดแอปได้ที่ไหนครับ",                "th", False),
    ("ลืม check in ต้องทำอะไรคะ",            "th", False),
    ("เงินเดือนออกวันไหนคะ",                "th", True),   # no payroll data in FAQ → should escalate
]

TROUBLESHOOTING_CASES = [
    # (emp_id, message, expected_root_cause)
    ("EMP004", "ยอด 0 บาท เบิกเงินไม่ได้",   "sync_pending"),
    ("EMP005", "เบิกไม่ได้ครับ",              "blacklisted"),
    ("EMP002", "ทำไมเบิกเงินไม่ได้",         "status_inactive"),
    ("EMP003", "เบิกเงินไม่ได้เลย",          "ok"),
    ("EMP001", "ทำไมยอดไม่อัปเดต",           "ok"),
    ("EMP001", "หักเงินเท่าไหร่",             "ok"),
]

# ── Helpers ────────────────────────────────────────────────────────────────────

SEP  = "─" * 110
THIN = "·" * 110

def _preview(text: str, width: int = 55) -> str:
    return text.replace("\n", " ")[:width]

def _route_label(decision) -> str:
    return decision.template_key or str(decision.route).replace("Route.", "")

# ── Section runners ────────────────────────────────────────────────────────────

def run_chitchat(tenant_id: str) -> tuple[int, int]:
    print(f"\n{'━'*110}")
    print("  CHITCHAT & MISSING INFO  —  instant template, zero LLM calls")
    print(f"{'━'*110}")
    print(f"  {'#':<4} {'Message':<30} {'Route label':<28} {'Pass?':<6} Response preview")
    print(THIN)

    passed = failed = 0

    all_cases = [(m, "missing_info") for m in MISSING_INFO_CASES]
    all_cases = [(m, exp) for m, exp in CHITCHAT_CASES] + all_cases

    for i, (message, expected_label) in enumerate(all_cases):
        lang     = detect_language(message)
        trace    = PipelineTrace(tenant_id=tenant_id, query=message, language=lang)
        intent_r = detect_intent(message, lang)
        decision = decide_route(intent_r.intent, message, lang, tenant_id)
        answer   = generate_answer(
            message=message, context="", language=lang,
            tenant_id=tenant_id, intent=intent_r.intent.value,
            history=[], route=str(decision.route),
            template_key=decision.template_key,
        )
        trace.set_route(str(decision.route), decision.reason, label=decision.template_key)
        trace.set_answer(answer.text, answer.grounding_score, answer.was_escalated)
        trace.flush()

        label  = _route_label(decision)
        route  = str(decision.route).replace("Route.", "")
        full   = f"{route}/{label}"
        ok     = label == expected_label
        mark   = "✅" if ok else "❌"
        if ok: passed += 1
        else:  failed += 1

        print(f"  {i+1:<4} {message:<30} {full:<28} {mark:<6} {_preview(answer.text, 40)}")

    print(THIN)
    print(f"  Passed: {passed}/{passed+failed}\n")
    return passed, failed


def run_faq(tenant_id: str) -> tuple[int, int]:
    from rag.retriever import retrieve, build_context

    print(f"\n{'━'*110}")
    print("  FAQ  —  retrieval + LLM answer")
    print(f"{'━'*110}")
    print(f"  {'#':<4} {'Question':<40} {'Score':>6}  {'E?':<4} Response preview")
    print(THIN)

    answered = escalated = 0

    for i, (question, lang, expect_escalated) in enumerate(FAQ_CASES):
        trace    = PipelineTrace(tenant_id=tenant_id, query=question, language=lang)
        intent_r = detect_intent(question, lang)
        decision = decide_route(intent_r.intent, question, lang, tenant_id)
        trace.set_route(str(decision.route), decision.reason, label=decision.template_key)
        try:
            result    = retrieve(question, tenant_id, lang, top_k=3)
            context   = build_context(result.documents, lang)
            top_score = result.documents[0].score if result.documents else 0.0
            trace.set_retrieval(result.query_used, result.collection, result.documents)
        except Exception as e:
            print(f"  {i+1:<4} {question:<40}  SKIP — {e}")
            continue

        answer = generate_answer(
            message=question, context=context, language=lang,
            tenant_id=tenant_id, intent="question",
            history=[], route=str(decision.route),
            top_retrieval_score=top_score,
        )
        trace.set_answer(answer.text, answer.grounding_score, answer.was_escalated)
        trace.flush()

        esc_flag = "ESC" if answer.was_escalated else "   "
        ok = answer.was_escalated == expect_escalated
        mark = "✅" if ok else "❌"

        if answer.was_escalated: escalated += 1
        else:                    answered  += 1

        print(f"  {i+1:<4} {question:<40} {answer.grounding_score:>6.2f}  {esc_flag:<4} {mark} {_preview(answer.text)}")

    print(THIN)
    print(f"  Answered: {answered}  |  Escalated: {escalated}/{answered+escalated}\n")
    return answered, escalated


def run_troubleshooting(tenant_id: str) -> tuple[int, int]:
    from agent.planner import run_troubleshooting_agent

    print(f"\n{'━'*110}")
    print("  TROUBLESHOOTING  —  agent diagnosis")
    print(f"{'━'*110}")
    print(f"  {'#':<4} {'Emp':<8} {'Message':<34} {'Root cause':<16} {'Pass?':<6} Answer preview")
    print(THIN)

    passed = failed = 0

    for i, (emp_id, message, expected) in enumerate(TROUBLESHOOTING_CASES):
        lang     = detect_language(message)
        trace    = PipelineTrace(tenant_id=tenant_id, query=message, language=lang)
        intent_r = detect_intent(message, lang)
        decision = decide_route(intent_r.intent, message, lang, tenant_id)
        trace.set_route(str(decision.route), decision.reason, label=decision.template_key)

        agent_result = run_troubleshooting_agent(
            employee_id=emp_id,
            issue=message,
            language=lang,
            tenant_id=tenant_id,
            sub_type=decision.template_key,
        )
        trace.set_troubleshooting(
            employee_id=emp_id,
            root_cause=agent_result["root_cause"],
            tools_used=agent_result["tools_used"],
        )
        system = TROUBLESHOOTING_SYSTEM.get(lang, TROUBLESHOOTING_SYSTEM["th"])
        answer = generate_answer(
            message=message,
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
        ok      = actual == expected
        mark    = "✅" if ok else "❌"
        if ok: passed += 1
        else:  failed += 1

        print(f"  {i+1:<4} {emp_id:<8} {message:<34} {actual:<16} {mark:<6} {_preview(answer.text)}")

    print(THIN)
    print(f"  Passed: {passed}/{passed+failed}\n")
    return passed, failed


# ── Main ───────────────────────────────────────────────────────────────────────

def run(tenant_id: str) -> None:
    print(f"\n{'═'*110}")
    print(f"  CS CHATBOT — Full pipeline test   tenant={tenant_id}   mock={os.environ.get('USE_MOCK_APIS','false')}")
    print(f"{'═'*110}")

    cc_pass, cc_fail   = run_chitchat(tenant_id)
    faq_ans, faq_esc   = run_faq(tenant_id)
    ts_pass, ts_fail   = run_troubleshooting(tenant_id)

    total_pass = cc_pass + faq_ans + ts_pass
    total_fail = cc_fail + ts_fail

    print(f"\n{'═'*110}")
    print("  SUMMARY")
    print(f"{'═'*110}")
    print(f"  Chitchat / missing_info : {cc_pass}/{cc_pass+cc_fail} correct labels")
    print(f"  FAQ                     : {faq_ans} answered  |  {faq_esc} escalated")
    print(f"  Troubleshooting         : {ts_pass}/{ts_pass+ts_fail} correct root causes")
    print(f"  Overall pass            : {total_pass}/{total_pass+total_fail}")
    print(f"{'═'*110}\n")
    print("  Full traces written to logs/faq_trace.log\n")


if __name__ == "__main__":
    os.environ.setdefault("USE_MOCK_APIS", "true")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="hns")
    args = parser.parse_args()
    run(args.tenant)
