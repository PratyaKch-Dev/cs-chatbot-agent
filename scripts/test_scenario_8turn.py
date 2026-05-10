"""
8-turn scenario test — checks text answers AND image attachments.

Usage:
    PYTHONPATH=. python scripts/test_scenario_8turn.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pipeline.orchestrator import handle_message

TENANT_ID   = "hns"
USER_ID     = "test_8turn_001"
EMPLOYEE_ID = "EMP001"

# (turn, message, note, expect_image, must_not_contain)
TURNS = [
    ("1", "สวัสดีครั",
     "chitchat greeting",
     False, ["ขออภัย ไม่มีข้อมูลในส่วนนี้"]),

    ("2", "สอบถามหน่อย",
     "preamble-only → AMBIGUOUS → clarification or greeting",
     False, ["ขออภัย ไม่มีข้อมูลในส่วนนี้"]),

    ("3", "ลงทะเบียนยังไงหรอครับ",
     "faq how-to — answer should mention ลงทะเบียน",
     False, ["ขออภัย ไม่มีข้อมูลในส่วนนี้"]),

    ("4", "ขอบคุณครับ",
     "chitchat thanks → END_FLOW",
     False, ["ขออภัย ไม่มีข้อมูลในส่วนนี้"]),

    ("5", "ขอวิถีเบิกเงินหน่อยครับ",
     "faq withdrawal — watch for เคลม mismatch",
     False, []),                       # known RAG gap — don't assert

    ("6", "เบิกเงินครับไม่ใช่เครม",
     "correction → TOPIC_SHIFT + clear cached_faq",
     False, []),                       # may still be no-data; key is it doesn't POISON turn 7

    ("7", "มีวิธีเปลี่ยนรหัสผ่านมั้ยครั",
     "new FAQ — must NOT get ขออภัย from cached_faq poison (data gap: no password doc in HNS)",
     False, ["ขออภัย ไม่มีข้อมูลในส่วนนี้"]),

    ("8", "ดีครับ",
     "chitchat within active context → greeting, NOT faq_followup",
     False, ["ขออภัย ไม่มีข้อมูลในส่วนนี้"]),
]

SEP = "─" * 74


def check(turn_num, answer, image_urls, expect_image, must_not_contain):
    issues = []
    for bad in must_not_contain:
        if bad in answer:
            issues.append(f"answer contains forbidden text: '{bad}'")
    if expect_image and not image_urls:
        issues.append("expected image attachment — none returned")
    if not expect_image and image_urls:
        pass  # extra image is OK, not a failure
    return issues


def run():
    print(f"\n{'='*74}")
    print("  8-TURN SCENARIO TEST  (text + image)")
    print(f"{'='*74}\n")

    fails = 0
    for num, message, note, expect_image, must_not in TURNS:
        print(SEP)
        print(f"  Turn {num}  [{note}]")
        print(f"  USER: {message}")
        print(SEP)

        result = handle_message(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            message=message,
            employee_id=EMPLOYEE_ID,
            return_trace=False,
        )

        issues = check(num, result.answer, result.image_urls, expect_image, must_not)

        print(f"  BOT : {result.answer[:300]}")
        if result.image_urls:
            print(f"  IMG : {result.image_urls}")
        else:
            print(f"  IMG : (none)")

        if issues:
            for i in issues:
                print(f"  ✗   {i}")
            fails += 1
        else:
            print(f"  ✓   OK")
        print()

    print(SEP)
    if fails == 0:
        print(f"  ALL TURNS PASSED")
    else:
        print(f"  {fails} TURN(S) FAILED")
    print(f"{'='*74}\n")


if __name__ == "__main__":
    run()
