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
    "เบิกเงินได้ตั้งแต่กี่โมงครับ",
    "เบิกได้กี่ครั้งต่อเดือนคะ",
    "เบิกได้สูงสุดเท่าไหร่",
    "เบิกขั้นต่ำต้องกี่บาทครับ",
    "วันหยุดเสาร์อาทิตย์เบิกเงินได้ไหมคะ",
    "เบิกได้ถึงวันที่เท่าไหร่ของเดือน",
    "เบิกแล้วเงินเข้าบัญชีไหนครับ",
    "กดเบิกไปแล้วแต่เงินยังไม่เข้าเลย รอนานแค่ไหน",
    "เงินไม่เข้ามาเกิน 1 วันแล้ว ต้องทำอะไรคะ",
    "อยากเปลี่ยนบัญชีรับเงิน ทำได้ไหม",
    # เงื่อนไข (Eligibility)
    "เพิ่งเข้างานได้ 3 วัน เบิกได้แล้วไหมครับ",
    "พนักงานใหม่ต้องรอกี่วันถึงใช้แอปได้",
    "วันที่ลาพักร้อน เบิกเงินได้ไหมคะ",
    "ลาป่วยอยู่ยังมีเงินเบิกไหม",
    "ทำ OT เพิ่มจะได้ยอดเบิกเพิ่มด้วยไหม",
    "ประกันสังคมหักออกจากยอดที่เบิกได้ด้วยไหมครับ",
    # การคำนวณยอด (Calculation)
    "ยอดเงินที่เบิกได้คิดมาจากอะไรครับ",
    "ระบบนับวันทำงานยังไง",
    "7 วันอายุงานนับจากวันไหน",
    "ทำ OT เมื่อวานแต่ยอดยังไม่เพิ่ม เป็นปกติไหม",
    # การชำระคืน (Repayment)
    "เงินที่เบิกไปจะหักคืนตอนไหนครับ",
    "ผ่อนชำระได้ไหม หรือต้องหักทีเดียวเลย",
    "มีดอกเบี้ยไหมถ้าเบิกเงินล่วงหน้า",
    # ปัญหาการใช้งาน (Issues)
    "เข้าแอปไม่ได้เลย ลงทะเบียนก็ไม่ผ่าน ทำไงดี",
    "ยอดเงินเป็น 0 บาท ทั้งที่ทำงานมาทุกวัน",
    "หัวหน้าตั้งกะงานให้แล้ว แต่ยอดยังไม่ขึ้นเลยครับ",
    "เปลี่ยนชื่อในระบบแล้วเข้าแอปไม่ได้",
    "แอปค้างอยู่เลย ระบบมีปัญหาไหม",
    # ทั่วไป (General)
    "ใช้แอปครั้งแรกต้องทำอะไรบ้างคะ",
    "อยากติดต่อแอดมินต้องทำยังไง",
    "ข้อมูลส่วนตัวในแอปปลอดภัยไหมครับ",
    # การเข้างาน — นโยบาย (Attendance policy)
    "ลืม check in วันนี้ ต้องแจ้งใครคะ",
    "check in ไปแล้วแต่ระบบไม่บันทึก ทำไงได้บ้าง",
    "ขาดงาน 1 วันหักเงินเดือนเท่าไหร่ครับ",
    "มาสายกี่นาทีถึงโดนหักครับ",
    # เงินเดือน / สลิป (Payroll)
    "เงินเดือนจะออกวันที่เท่าไหร่คะ",
    "สลิปเงินเดือนดูได้จากไหนครับ",
    "ภาษีเดือนนี้ถูกหักไปเท่าไหร่",
    # บัญชีผู้ใช้ (Account management)
    "เบอร์โทรเปลี่ยนแล้วต้องแจ้งยังไงครับ",
    "ลืมรหัสผ่านแอป จะ reset ยังไงคะ",
    # English questions
    "how much can I withdraw at most?",
    "I want to change my bank account, how do I do that?",
    "what do I need to sign up for Salary Hero?",
    "why is my withdrawable balance lower than expected?",
    "is my data safe on this app?",
    "how can I reach support?",
    "I withdrew but the money hasn't arrived, what should I do?",
    "can I withdraw on a Sunday?",
]

SECTIONS = {
    0:  "การเบิกเงิน (Withdrawal)",
    10: "เงื่อนไข (Eligibility)",
    16: "การคำนวณยอด (Calculation)",
    20: "การชำระคืน (Repayment)",
    23: "ปัญหาการใช้งาน (Issues)",
    28: "ทั่วไป (General)",
    31: "การเข้างาน — นโยบาย (Attendance policy)",
    35: "เงินเดือน / สลิป (Payroll)",
    38: "บัญชีผู้ใช้ (Account management)",
    40: "English questions",
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
        top_score = result.documents[0].score if result.documents else 0.0

        answer = generate_answer(
            q, context, lang, tenant_id, "question", [], str(decision.route),
            top_retrieval_score=top_score,
        )
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
