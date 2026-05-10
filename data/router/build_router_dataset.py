"""
Build router training dataset.

Sources:
  - data/faqs/solutions_faq.csv  → faq examples (Question column)
  - HAND_CRAFTED dict below      → chitchat / troubleshooting / missing_info

Output:
  data/router/router_train_auto.csv  (text, label)

After generation, review and copy to router_train.csv before training.
Run:  python data/router/build_router_dataset.py
"""

import csv
import random
from pathlib import Path

SEED = 42
FAQ_CAP = 80  # max faq examples to keep class balance manageable

HAND_CRAFTED: dict[str, list[str]] = {
    "chitchat_greeting": [
        "สวัสดีครับ", "สวัสดีค่ะ", "หวัดดีครับ", "หวัดดีค่ะ", "ดีจ้า",
        "ดีครับ", "สวัสดีตอนเช้า", "สวัสดีตอนบ่าย", "สวัสดีตอนเย็น",
        "อรุณสวัสดิ์ครับ", "สวัสดีนะคะ", "หวัดดีนะ", "ทักทายหน่อย",
        "hi", "hello", "hey", "good morning", "good afternoon",
        "good evening", "hi there", "hey there", "howdy",
        "สวัสดีๆ", "โอ้โห สวัสดี", "เฮ้", "ฮัลโหล",
        "hello ครับ", "hi ค่ะ", "ดีๆ", "เฮ้โล",
    ],
    "chitchat_thanks": [
        "ขอบคุณ", "ขอบคุณมาก", "ขอบคุณค่ะ", "ขอบคุณครับ", "ขอบคุณนะ",
        "ขอบใจ", "ขอบใจมาก", "ขอบคุณมากๆ", "ขอบคุณมากเลย",
        "ขอบคุณที่ช่วย", "ขอบคุณที่ตอบ", "ขอบคุณที่ให้ข้อมูล",
        "thanks", "thank you", "thank you so much", "thanks a lot",
        "many thanks", "appreciate it", "ty", "thx",
        "ขอบพระคุณครับ", "ขอบพระคุณค่ะ", "ขอบคุณสำหรับข้อมูล",
        "ขอบคุณมากนะคะ", "ขอบคุณครับผม", "ขอบคุณที่แจ้ง",
    ],
    "chitchat_goodbye": [
        "ลาก่อน", "ลาก่อนครับ", "ลาก่อนค่ะ", "บาย", "บายๆ",
        "แล้วเจอกัน", "แล้วเจอกันใหม่", "แล้วกัน", "ไปก่อนนะ",
        "ไปก่อนครับ", "ไปก่อนค่ะ", "โอเคบาย", "โอเค บาย",
        "bye", "goodbye", "see you", "see you later", "take care",
        "good bye", "bye bye", "cya", "ttyl",
        "ขอตัวก่อนนะ", "ขอตัวก่อนครับ", "ขอตัวก่อนค่ะ",
        "โอเค แล้วกัน", "เดี๋ยวว่าใหม่นะ",
    ],
    "chitchat_frustrated": [
        "แย่มากเลย", "ห่วยมาก", "บ้าอะไร", "ทำไมถึงเป็นแบบนี้",
        "หัวร้อนมาก", "น่าเบื่อมาก", "ไม่ไหวแล้ว", "เหนื่อยมาก",
        "รำคาญมากเลย", "ทำไมแอปมันห่วยแบบนี้", "ใช้ไม่ได้เลย",
        "ทำไมต้องยากขนาดนี้", "ทำไมมันช้าแบบนี้", "ทดสอบไม่ผ่านสักที",
        "so annoying", "this is terrible", "awful", "this is so frustrating",
        "i'm so frustrated", "why is this so hard", "this app is broken",
        "not working at all", "worst app ever", "so slow",
        "โกรธมากเลย", "หัวร้อน", "แย่จริงๆ", "ทนไม่ไหวแล้ว",
    ],
    "chitchat_confused": [
        "ไม่เข้าใจ", "งงมาก", "งงเลย", "งงหน่อย", "ทำไมนะ",
        "ไม่เข้าใจเลย", "อธิบายได้ไหม", "ช่วยอธิบายหน่อย",
        "หมายความว่าอะไร", "แปลว่าอะไร", "คืออะไร",
        "confused", "don't understand", "i'm confused",
        "what do you mean", "can you explain", "i don't get it",
        "what does this mean", "please explain", "not sure what this means",
        "งงงงง", "ไม่ค่อยเข้าใจ", "อ่านแล้วยังงง", "ทำความเข้าใจไม่ได้",
        "ขอความกระจ่างหน่อย", "สับสนนิดนึง",
    ],
    "missing_info": [
        "ช่วยด้วย", "ช่วยหน่อย", "มีปัญหา", "ปัญหา", "ไม่ได้",
        "ใช้ไม่ได้", "มีปัญหานะ", "ช่วยดูหน่อย",
        "help", "problem", "issue", "need help",
        "something wrong", "not working", "help me",
        "ขอความช่วยเหลือ", "ต้องการความช่วยเหลือ", "ช่วยด้วยนะครับ",
        "ช่วยด้วยค่ะ", "แก้ไขหน่อย", "ตรวจสอบหน่อย",
        "ดูให้ทีนะ", "ช่วยดูให้ที", "โอ้โห", "อ่ะ",
        "เออ", "อืม", "อ้าว", "เหรอ",
    ],
    "troubleshooting_withdrawal": [
        "เบิกเงินไม่ได้", "เบิกไม่ได้เลย", "เบิกเงินไม่ผ่าน",
        "ยอด 0", "ยอด0 บาท", "ยอดเป็น 0", "ยอดแสดงเป็น 0",
        "ยอดไม่ขึ้น", "เงินไม่ขึ้น", "ไม่มียอดเบิก",
        "ทำไมเบิกเงินไม่ได้", "ยังเบิกไม่ได้เลย", "เบิกไม่ผ่านสักที",
        "กดเบิกแล้วมันไม่ผ่าน", "เบิกไม่ได้ทำไม",
        "ยอดเงินเป็น 0 บาท", "ยอดแสดง 0 บาท", "ยอดเงินหาย",
        "can't withdraw", "cannot withdraw", "withdrawal not working",
        "zero balance", "balance is 0", "balance showing 0",
        "withdrawal failed", "not eligible to withdraw",
        "เบิกไม่ผ่านครับ", "เบิกไม่ได้ค่ะ", "ยอดหาย",
        "เบิกเงินไม่ผ่านเลย", "เบิกเงินได้แค่บางส่วน",
    ],
    "troubleshooting_signup": [
        "สมัครไม่ได้", "ลงทะเบียนไม่ได้", "สมัครไม่สำเร็จ",
        "ลงทะเบียนไม่สำเร็จ", "สมัครใช้งานไม่ได้", "เปิดบัญชีไม่ได้",
        "register ไม่ได้", "สมัครแล้วมันขึ้นว่าไม่สำเร็จ",
        "ทำไมสมัครไม่ได้", "สมัครไม่ผ่าน", "ลงทะเบียนไม่ผ่าน",
        "can't sign up", "cannot register", "sign up failed",
        "registration failed", "can't create account",
        "account creation failed", "signup not working",
        "สมัครแอปไม่ได้", "ยืนยันตัวตนไม่ผ่าน", "สมัครไม่ได้เลยสักที",
        "สมัครสมาชิกไม่ได้", "สร้างบัญชีไม่ได้",
    ],
    "troubleshooting_cant_find_company": [
        "หาบริษัทไม่เจอ", "ค้นหาบริษัทไม่เจอ", "บริษัทไม่ขึ้น",
        "บริษัทหายไป", "ไม่เจอบริษัทตัวเอง", "บริษัทไม่อยู่ในระบบ",
        "ค้นชื่อบริษัทไม่เจอ", "หาชื่อบริษัทไม่เจอ",
        "company not found", "can't find my company",
        "company not showing up", "my company is not in the list",
        "company not in system", "can't find company name",
        "company disappeared", "company missing from app",
        "ค้นหาบริษัทไม่ได้", "หาบริษัทไม่ได้เลย", "ไม่มีบริษัทของฉัน",
        "บริษัทไม่ขึ้นมาเลย", "กรอกชื่อบริษัทแล้วไม่เจอ",
    ],
    "troubleshooting_money_not_arrived": [
        "เงินยังไม่เข้า", "รอเงินนานมาก", "เงินยังไม่โอน",
        "โอนเงินแล้วยังไม่ได้รับ", "ยังไม่ได้รับเงิน",
        "เงินไม่เข้าบัญชี", "เงินหายไป", "เงินไม่มาสักที",
        "เบิกแล้วแต่เงินยังไม่เข้า", "รอเงินอยู่แต่ยังไม่ได้",
        "money not received", "transfer not arrived",
        "money not in account", "withdrawal processed but no money",
        "money still not credited", "funds not received",
        "transaction successful but money missing",
        "เงินยังไม่ถึง", "เงินยังไม่โอนมา", "ยังไม่เห็นเงินในบัญชี",
        "เงินเข้าช้า", "รอเงินมานานแล้ว",
    ],
}


def load_faq_questions(csv_path: Path, cap: int = FAQ_CAP) -> list[str]:
    questions = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            q = (row.get("Question") or row.get("question") or "").strip()
            if q and len(q) >= 5:
                questions.append(q)
    random.shuffle(questions)
    return questions[:cap]


def build(out_path: Path) -> None:
    faq_csv = Path(__file__).parents[2] / "data" / "faqs" / "solutions_faq.csv"
    faq_questions = load_faq_questions(faq_csv)

    rows: list[tuple[str, str]] = []
    for label, examples in HAND_CRAFTED.items():
        for text in examples:
            rows.append((text.strip(), label))

    for q in faq_questions:
        rows.append((q, "faq"))

    random.seed(SEED)
    random.shuffle(rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        writer.writerows(rows)

    label_counts: dict[str, int] = {}
    for _, label in rows:
        label_counts[label] = label_counts.get(label, 0) + 1

    print(f"Written {len(rows)} rows to {out_path}")
    for label, count in sorted(label_counts.items()):
        print(f"  {label:45s} {count:4d}")


if __name__ == "__main__":
    out = Path(__file__).parent / "router_train_auto.csv"
    build(out)
    print(f"\nReview {out} then copy to router_train.csv before training.")
