"""
FAQ batch tester.

Runs a set of test questions through the full pipeline and prints a summary table.
Results are also written to logs/faq_trace.log as usual.

Usage:
    PYTHONPATH=. python scripts/test_faq.py
    PYTHONPATH=. python scripts/test_faq.py --tenant hns --lang th
"""

import argparse
import time

from dotenv import load_dotenv
load_dotenv()

from utils.language import detect_language
from utils.pipeline_logger import PipelineTrace
from pipeline.router import decide_route
from rag.retriever import retrieve, build_context
from pipeline.answer_generator import generate_answer

TEST_QUESTIONS = [
    # การเบิกเงิน (Withdrawal)
    "เบิกเงินได้กี่โมงถึงกี่โมง",
    "เบิกได้กี่ครั้งต่อรอบ",
    "เบิกได้สูงสุดเท่าไหร่",
    "เบิกขั้นต่ำเท่าไหร่",
    "เบิกเงินได้วันไหนบ้าง วันหยุดเบิกได้ไหม",
    "เบิกได้ถึงวันที่เท่าไหร่",
    "เงินเข้าบัญชีไหน",
    "ยอดเงินเข้าตอนไหน เบิกแล้วทำไมไม่เข้า",
    "หากเงินไม่เข้าเกิน 24 ชั่วโมงต้องทำอย่างไร",
    "ขอเปลี่ยนบัญชีได้ไหม",
    # เงื่อนไข (Eligibility)
    "ทำงานกี่วันถึงใช้งานได้",
    "พนักงานใหม่เบิกได้ไหม",
    "ลางานเบิกได้ไหม",
    "ลาป่วยได้เงินเบิกไหม",
    "OT รวมในการคำนวณยอดเบิกไหม",
    "ประกันสังคมและภาษีหักจากยอดเบิกไหม",
    # การคำนวณยอด (Calculation)
    "ยอดเงินที่สามารถเบิกได้คำนวณอย่างไร",
    "วันทำงานจริงคำนวณอย่างไร",
    "นับ 7 วันอายุงานจากวันไหน",
    "ทำ OT แล้วเงินเบิกเพิ่มไหม",
    # การชำระคืน (Repayment)
    "หักเงินคืนอย่างไร",
    "สามารถผ่อนชำระเงินที่เบิกได้ไหม",
    "มีดอกเบี้ยในการเบิกไหม",
    # ปัญหาการใช้งาน (Issues)
    "เข้าใช้งานไม่ได้ ลงทะเบียนไม่ได้",
    "ไม่มียอดเงินเบิก เงินไม่ขึ้น",
    "หัวหน้าตั้งกะงานให้แล้วแต่ยอดไม่ขึ้น",
    "เปลี่ยนชื่อ-สกุลแล้วใช้งานไม่ได้",
    "ระบบขัดข้องทำอย่างไร",
    # ทั่วไป (General)
    "ใช้งานครั้งแรกต้องทำอย่างไร",
    "ติดต่อแอดมินอย่างไร",
    "ข้อมูลส่วนตัวปลอดภัยไหม",
]

SECTIONS = {
    0:  "การเบิกเงิน (Withdrawal)",
    10: "เงื่อนไข (Eligibility)",
    16: "การคำนวณยอด (Calculation)",
    20: "การชำระคืน (Repayment)",
    23: "ปัญหาการใช้งาน (Issues)",
    28: "ทั่วไป (General)",
}

COL_Q  = 36
COL_A  = 55
COL_SC = 7


def run(tenant_id: str, language: str) -> None:
    print(f"\nTenant: {tenant_id}  Lang: {language}  Questions: {len(TEST_QUESTIONS)}\n")
    print(f"{'#':<4} {'Question':<{COL_Q}} {'Score':>{COL_SC}} {'E?':<4} Answer preview")
    print("─" * 120)

    passed = escalated = 0

    for i, q in enumerate(TEST_QUESTIONS):
        if i in SECTIONS:
            print(f"\n  ── {SECTIONS[i]} ──")

        lang = detect_language(q) if language == "auto" else language
        trace = PipelineTrace(tenant_id=tenant_id, query=q, language=lang)

        decision = decide_route("question", q, lang, tenant_id)
        trace.set_route(str(decision.route), decision.reason)

        result = retrieve(q, tenant_id, lang, top_k=3)
        trace.set_retrieval(result.query_used, result.collection, result.documents)
        context = build_context(result.documents, lang)

        answer = generate_answer(q, context, lang, tenant_id, "question", [], str(decision.route))
        trace.set_answer(answer.text, answer.grounding_score, answer.was_escalated)
        trace.flush()

        flag = "YES" if answer.was_escalated else "   "
        preview = answer.text.replace("\n", " ")[:COL_A]
        q_short = q[:COL_Q]

        print(f"{i+1:<4} {q_short:<{COL_Q}} {answer.grounding_score:>{COL_SC}.2f} {flag:<4} {preview}")

        if answer.was_escalated:
            escalated += 1
        else:
            passed += 1

    print("\n" + "─" * 120)
    print(f"  Total: {len(TEST_QUESTIONS)}  |  Answered: {passed}  |  Escalated (no data): {escalated}")
    print(f"  Coverage: {passed / len(TEST_QUESTIONS) * 100:.0f}%")
    print()
    print("  Full traces written to logs/faq_trace.log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="hns")
    parser.add_argument("--lang", default="th", choices=["th", "en", "auto"])
    args = parser.parse_args()
    run(args.tenant, args.lang)
