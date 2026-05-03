"""
Request router — LLM decides everything.

One fast haiku call (~150ms, max_tokens=10) classifies the message into
a specific label, which maps directly to a route + template_key.

Labels:
  greeting / thanks / goodbye / frustrated / confused  →  CHITCHAT
  missing_info                                          →  MISSING_INFO
  troubleshooting_withdrawal                            →  TROUBLESHOOTING
  troubleshooting_attendance                            →  TROUBLESHOOTING
  troubleshooting_account                               →  TROUBLESHOOTING
  troubleshooting_deduction                             →  TROUBLESHOOTING
  faq                                                   →  FAQ

Fallback (LLM unavailable): use detect_intent result → same label map.
"""

import json
import logging
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

_logger = logging.getLogger("pipeline.router")


class Route(str, Enum):
    FAQ            = "faq"
    TROUBLESHOOTING = "troubleshooting"
    DIRECT         = "direct"
    TEMPLATE       = "template"       # kept for backward compat
    CHITCHAT       = "chitchat"
    MISSING_INFO   = "missing_info"


@dataclass
class RouteDecision:
    route: Route
    reason: str
    confidence: float = 1.0
    template_key: str = ""
    existing_context: Optional[str] = None
    conv_state: str = "new_query"           # new_query | followup | ambiguous
    followup_type: Optional[str] = None     # faq_followup | troubleshooting_recheck | None
    search_query: str = ""                  # synthesized RAG query (router-generated)


# ── Label → Route map (single source of truth) ────────────────────────────────
_LABEL_TO_ROUTE: dict[str, Route] = {
    "greeting":                    Route.CHITCHAT,
    "thanks":                      Route.CHITCHAT,
    "goodbye":                     Route.CHITCHAT,
    "frustrated":                  Route.CHITCHAT,
    "confused":                    Route.CHITCHAT,
    "missing_info":                Route.MISSING_INFO,
    "troubleshooting_withdrawal":  Route.TROUBLESHOOTING,
    # Add new subtypes here when ready
    "faq":                         Route.FAQ,
}

# Intent → label (for fallback when LLM is unavailable)
_INTENT_TO_LABEL: dict[str, str] = {
    "greeting":   "greeting",
    "thanks":     "thanks",
    "goodbye":    "goodbye",
    "frustrated": "frustrated",
    "confused":   "confused",
    "unclear":    "missing_info",
    "question":   "faq",
}

# Kept for backward compat
CHITCHAT_INTENTS    = {"greeting", "thanks", "goodbye", "frustrated", "confused"}
MISSING_INFO_INTENTS = {"unclear"}
TEMPLATE_INTENTS    = CHITCHAT_INTENTS | MISSING_INFO_INTENTS


# ── LLM classifier ────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """\
Salary Hero chatbot router. Return JSON only.

━━ INTENTS ━━
CHITCHAT (no search needed):
  greeting | thanks | goodbye | frustrated | confused

MISSING_INFO (no search needed):
  missing_info — message too vague/short to answer (e.g. "อ่ะ", "หา", single word with no topic)

TROUBLESHOOTING (needs live data lookup — VERY narrow scope):
  troubleshooting_withdrawal — ONLY when user's available withdrawal BALANCE shows 0 / wrong amount / not updating
    USE ONLY when: ยอด 0 / ยอดเบิกได้เป็น 0 / ยอดไม่ขึ้นหลังสแกน / ยอดไม่อัปเดต / ทำไมเบิกไม่ได้เลย (implies balance 0) / ทำไมยังเบิกเงินไม่ได้ / ทำไมถึยังเบิก / เบิกไม่ได้เลย / ยังเบิกไม่ได้ / ยังคงเบิกไม่ได้
    DO NOT use for: ส่งคำขอเบิกไม่ผ่าน / คำขอถูกปฏิเสธ / ยังไม่ได้รับเงิน / ชำระคืนไม่ได้ / เคลมไม่สำเร็จ / ถูกระงับ / ยอดติดลบ / OTP ไม่มา / เบอร์โทรใช้ไม่ได้ / บริษัทหาไม่เจอ → these all have FAQ articles

FAQ (general knowledge AND personal-problem questions that have static FAQ articles):
  faq — use for everything except balance-is-0 troubleshooting
    includes: วิธีทำ / เงื่อนไข / ขั้นตอน / สถานะ / ประวัติ / ข้อผิดพลาด / ปัญหาทั่วไป / HR changes / FlexBen

━━ KEY DISTINCTIONS ━━
"ยอดเบิกได้เป็น 0 / ยอดไม่ขึ้น"         → troubleshooting_withdrawal  (balance data — needs live lookup)
"เบิกเงินไปแล้วแต่ยังไม่ได้รับ"          → faq  (article: ไม่ได้รับเงินที่เบิก)
"กดส่งคำขอเบิกแล้วขึ้น error"            → faq  (article: ส่งคำขอเบิกเงินไม่สำเร็จ)
"คำขอเบิกเงิน/เคลมโดนปฏิเสธ"            → faq  (article: คำขอโดนปฏิเสธ / โดนปฏิเสธคำขอ)
"ชำระคืนไม่ได้ / ชำระอัตโนมัติไม่ผ่าน"  → faq  (article: ไม่สามารถชำระคืนได้)
"ยอดเงินติดลบ"                           → faq  (article: ยอดเงินติดลบ)
"ถูกระงับ / เงื่อนไขระงับ"               → faq  (article: ตรวจสอบเงื่อนไขการถูกระงับใช้งาน)
"ยื่นคำขอเคลมไม่สำเร็จ"                 → faq  (article: ยื่นคำขอไม่สำเร็จ)
"หาบริษัทตัวเองในแอปไม่เจอ"             → faq  (article: วิธีค้นหาบริษัทของคุณ)
"บริษัทไม่พบในแอป ทั้งที่ลงทะเบียนแล้ว" → faq  (article: บริษัทลงทะเบียนแล้วแต่หาชื่อไม่พบ)

━━ RULES ━━
greeting+question → classify by the question, not the greeting
preamble+question (สอบถามหน่อย / ขอถามหน่อย / อยากสอบถาม + actual question) → classify by the question only, ignore the preamble
unsure troubleshooting subtype → troubleshooting_withdrawal

conv_state: new_query=new topic | followup=continues active context | ambiguous=unclear short msg
  followup examples: "ขอลิงค์ ios" after bot gave app links | "แล้ว android ล่ะ" after iOS discussion
followup_type: faq_followup|troubleshooting_recheck|null  (null unless conv_state=followup)
troubleshooting_recheck when: แจ้ง HR แล้ว / ช่วยเช็คอีกที / ตอนนี้ปกติหรือยัง / ยังไม่ได้

search_query: rewrite the user's intent using EXACT FAQ article title vocabulary so embedding search finds it.
  Rules:
  1. Use exact article title words — tested vocabulary:
     ── Registration / login ──
     ลงทะเบียนด้วยรหัสพนักงาน | ลงทะเบียนด้วยเลขบัตรประชาชน | ลงทะเบียนใช้งาน Salary Hero
     วิธีการเข้าสู่ระบบ | ไม่พบข้อมูลผู้ใช้บนระบบ | เบอร์โทรศัพท์ไม่สามารถใช้งานได้ | ไม่ได้รับรหัส OTP
     วิธีค้นหาบริษัทของคุณ | บริษัทลงทะเบียนแล้วแต่หาชื่อไม่พบ | บริษัทยังไม่ได้ลงทะเบียนกับ Salary Hero
     ── Phone / password ──
     เปลี่ยนเบอร์ด้วยรหัสพนักงานและเลขบัตรประชาชน | เปลี่ยนเบอร์ด้วยเบอร์โทรศัพท์ใหม่ | ลืมรหัสผ่าน | วิธีเปลี่ยนรหัสผ่าน
     ── Bank account ──
     วิธีการผูกบัญชีธนาคาร | ผูกบัญชีธนาคารไม่สำเร็จ | ไม่มีเลขที่บัญชีรับเงิน | วิธีเปลี่ยนบัญชีธนาคารที่รับเงิน
     ขั้นตอนชำระเงินคืน | ไม่สามารถชำระคืนได้ | ชำระคืนเรียบร้อยแต่ยังไม่สามารถใช้งานได้
     ── SOD withdrawal ──
     วิธีเบิกค่าจ้างล่วงหน้า | เงื่อนไขการเบิกค่าจ้างล่วงหน้า | ติดตามสถานะการเบิก | ไม่มียอดเงินอัปเดต
     ไม่ได้รับเงินที่เบิก | ส่งคำขอเบิกเงินไม่สำเร็จ | คำขอโดนปฏิเสธ | เงื่อนไขการหักเงินคืน
     อายุงานยังไม่ครบ 7 วัน | อัปเดตแอป Salary Hero เวอร์ชันใหม่ | วิธีเช็คประวัติการเบิกย้อนหลัง
     ── Suspension / coupon ──
     ตรวจสอบเงื่อนไขการถูกระงับใช้งาน | เงื่อนไขถูกระงับการใช้งาน
     วิธีชวนเพื่อนมาใช้ Salary Hero | ไม่ได้รับคูปองชวนเพื่อน | ไม่ได้รับคูปองตรวจสุขภาพทางการเงิน
     ── FlexBen ──
     ขั้นตอนการเคลม | ยื่นคำขอไม่สำเร็จ | โดนปฏิเสธคำขอ | ยอดเงินติดลบ | สิทธิ์การเบิกเคลมสำหรับช่วงทดลองงาน
     ขั้นตอนยกเลิกการเคลม | ระยะเวลาเคลม | สถานะการเคลม | ตรวจสอบประวัติการเคลม
     ── HR changes ──
     ย้ายบริษัทในเครือ Essilor | การเปลี่ยนสัญญาจ้าง | การเปลี่ยนกลุ่มรอบการจ่ายค่าจ้าง | ปรับตำแหน่งงาน
     สิทธิ์การเบิกเคลมสำหรับช่วงทดลองงาน | พนักงานใหม่ทำงานไม่ถึงปี
  2. Expand short follow-up using history topic.
  3. Remove filler: ครับ ค่ะ นะ หน่อย อยากรู้ ต้องการ ช่วย
  4. ดาวน์โหลด/ลิงค์/แอป/สมัคร (personal registration) → "วิธีลงทะเบียน ดาวน์โหลดแอป".
     BUT: หาบริษัทไม่เจอ / บริษัทหาไม่พบ → "วิธีค้นหาบริษัทของคุณ" (NOT registration).
  5. ค่าธรรมเนียม/เงื่อนไข/กี่บาท/สูงสุด about withdrawal → "เงื่อนไขการเบิกค่าจ้างล่วงหน้า".
  6. เคลม/สวัสดิการ → use FlexBen titles (ขั้นตอนการเคลม, โดนปฏิเสธคำขอ, ระยะเวลาเคลม, etc.).
     เคลม ≠ เบิก — do NOT use withdrawal titles for FlexBen questions and vice versa.
  7. HR changes (ย้ายบริษัท / เปลี่ยนสัญญา / รอบจ่ายเงิน / ปรับตำแหน่ง) → use exact HR article titles.
  Examples (all validated against retrieval):
    "ขอลิงค์ ios"                              → "วิธีลงทะเบียน ดาวน์โหลดแอป"
    "สมัครใช้งานยังไง"                         → "ลงทะเบียนใช้งาน Salary Hero"
    "เคยลงทะเบียนแล้วแต่เข้าแอปไม่ได้"         → "วิธีการเข้าสู่ระบบ"
    "แอปบอกไม่พบข้อมูลผู้ใช้"                  → "ไม่พบข้อมูลผู้ใช้บนระบบ"
    "เบอร์โทรใช้ไม่ได้ในแอป"                   → "เบอร์โทรศัพท์ไม่สามารถใช้งานได้"
    "หาบริษัทตัวเองในแอปไม่เจอ"                → "วิธีค้นหาบริษัทของคุณ"
    "ในแอปบอกหาชื่อบริษัทไม่พบ"                → "บริษัทลงทะเบียนแล้วแต่หาชื่อไม่พบ"
    "บริษัทยังไม่ได้สมัครใช้ Salary Hero"       → "บริษัทยังไม่ได้ลงทะเบียนกับ Salary Hero"
    "เปลี่ยนเบอร์ได้ไหม"                        → "เปลี่ยนเบอร์ด้วยรหัสพนักงานและเลขบัตรประชาชน"
    "ไม่มีเบอร์เก่า"                            → "เปลี่ยนเบอร์ด้วยเบอร์โทรศัพท์ใหม่"
    "ผูกบัญชีธนาคาร"                            → "วิธีการผูกบัญชีธนาคาร"
    "ผูกบัญชีไม่ได้"                            → "ผูกบัญชีธนาคารไม่สำเร็จ"
    "ยังไม่มีบัญชีรับเงินในระบบ"                → "ไม่มีเลขที่บัญชีรับเงิน"
    "เปลี่ยนบัญชีรับเงิน"                       → "วิธีเปลี่ยนบัญชีธนาคารที่รับเงิน"
    "ชำระเงินคืนอัตโนมัติไม่ผ่าน"               → "ขั้นตอนชำระเงินคืน"
    "ชำระคืนไม่ได้"                              → "ไม่สามารถชำระคืนได้"
    "ชำระคืนแล้วแต่ยังใช้งานไม่ได้"             → "ชำระคืนเรียบร้อยแต่ยังไม่สามารถใช้งานได้"
    "วิธีเบิกเงิน"                              → "วิธีเบิกค่าจ้างล่วงหน้า"
    "เบิกได้กี่บาท / ค่าธรรมเนียม / เงื่อนไขเบิก" → "เงื่อนไขการเบิกค่าจ้างล่วงหน้า"
    "เบิกเงินไปแล้วแต่ยังไม่ได้รับ"             → "ไม่ได้รับเงินที่เบิก"
    "กดส่งคำขอเบิกแล้วขึ้น error"               → "ส่งคำขอเบิกเงินไม่สำเร็จ"
    "คำขอเบิกเงินโดนปฏิเสธ"                     → "คำขอโดนปฏิเสธ"
    "สถานะการเบิก"                              → "ติดตามสถานะการเบิก"
    "ดูประวัติการเบิกย้อนหลัง"                  → "วิธีเช็คประวัติการเบิกย้อนหลัง"
    "หักเงินคืน / เงื่อนไขหักเงิน"              → "เงื่อนไขการหักเงินคืน"
    "อัปเดตเวอร์ชันใหม่ / มีอะไรเปลี่ยน"        → "อัปเดตแอป Salary Hero เวอร์ชันใหม่"
    "ทำงานมาได้ไม่กี่วัน / อายุงานไม่ถึง 7 วัน" → "อายุงานยังไม่ครบ 7 วัน"
    "ถูกระงับ / เงื่อนไขระงับ"                  → "ตรวจสอบเงื่อนไขการถูกระงับใช้งาน"
    "ชวนเพื่อนใช้แอปยังไง"                      → "วิธีชวนเพื่อนมาใช้ Salary Hero"
    "ชวนเพื่อนแล้วไม่ได้คูปอง"                  → "ไม่ได้รับคูปองชวนเพื่อน"
    "ทำแบบทดสอบสุขภาพการเงินแล้วไม่ได้คูปอง"    → "ไม่ได้รับคูปองตรวจสุขภาพทางการเงิน"
    "เคลมสวัสดิการยังไงครับ / ขั้นตอนเคลม"      → "ขั้นตอนการเคลม"
    "ยื่นคำขอเคลมไม่สำเร็จ"                     → "ยื่นคำขอไม่สำเร็จ"
    "คำขอเคลมโดนปฏิเสธ"                         → "โดนปฏิเสธคำขอ"
    "ยอดเงินติดลบ"                               → "ยอดเงินติดลบ"
    "ทดลองงาน / เพิ่งทำงานใหม่ + เคลม/เบิก"     → "สิทธิ์การเบิกเคลมสำหรับช่วงทดลองงาน"
    "ยกเลิกการเคลม"                              → "ขั้นตอนยกเลิกการเคลม"
    "เคลมได้ถึงวันไหน / deadline"               → "ระยะเวลาเคลม"
    "สถานะการเคลมหมายความว่าอะไร"               → "สถานะการเคลม"
    "ดูประวัติการเคลมย้อนหลัง"                  → "ตรวจสอบประวัติการเคลม"
    "ย้ายบริษัทในเครือ"                          → "ย้ายบริษัทในเครือ Essilor"
    "เปลี่ยนสัญญาจ้าง"                          → "การเปลี่ยนสัญญาจ้าง"
    "โอนย้ายรอบจ่ายเงินเดือน / เปลี่ยนรอบจ่าย" → "การเปลี่ยนกลุ่มรอบการจ่ายค่าจ้าง"
    "ปรับตำแหน่ง / โปรโมท"                      → "ปรับตำแหน่งงาน"
    "OTP ไม่มา"                                  → "OTP ไม่มาต้องทำอย่างไร"
    "ยอดไม่ขึ้น" (after withdrawal)              → "ไม่มียอดเงินอัปเดต"
    "ลืมรหัส PIN / รีเซ็ต PIN"                          → "ลืมรหัสผ่าน"
    "แอปค้าง / แอปโหลดไม่ขึ้น / แอปปิดเอง"              → "แอปค้าง"
    "ตัวอักษรในแอปเล็ก/ใหญ่เกินไป / มองไม่เห็นตัวหนังสือ" → "ขนาดตัวอักษรผิดปกติ"
    "ขอลิงค์ดาวน์โหลด / โหลดแอปได้ที่ไหน"               → "ลงทะเบียนด้วยเลขบัตรประชาชนและเบอร์โทรศัพท์"
  Use "" for chitchat/missing_info

{"intent":"<label>","conv_state":"new_query|followup|ambiguous","followup_type":"faq_followup|troubleshooting_recheck|null","search_query":"<phrase>","confidence":0.0,"reason":"<short>"}"""


def _parse_label(raw: str) -> Optional[str]:
    """Extract a valid label from raw LLM output (used by fallback path)."""
    cleaned = re.sub(r"[^\w]", "", raw.strip().lower())
    if cleaned in _LABEL_TO_ROUTE:
        return cleaned
    for label in sorted(_LABEL_TO_ROUTE, key=len, reverse=True):
        if label in cleaned:
            return label
    return None


def _parse_router_json(raw: str) -> Optional[dict]:
    """
    Extract JSON from LLM output.
    Falls back to per-field regex extraction when JSON is truncated.
    """
    text = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Full parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Complete {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    # Per-field regex — handles truncated JSON
    result: dict = {}
    for key in ("intent", "conv_state", "followup_type", "search_query", "reason"):
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
        if m:
            result[key] = m.group(1)
    m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    if m:
        result["confidence"] = float(m.group(1))
    if "followup_type" not in result and re.search(r'"followup_type"\s*:\s*null', text):
        result["followup_type"] = None

    return result if "intent" in result else None


def _llm_classify(
    message: str,
    language: str,
    recent_history: list[dict] | None = None,
    active_context: str = "",
    summary: str = "",
) -> Optional[RouteDecision]:
    """
    Call fast LLM to classify message + conv_state.
    Returns None on failure so the caller uses the intent-based fallback.
    """
    try:
        from llm.client import call_llm

        parts: list[str] = []

        if summary:
            parts.append(f"Summary:\n{summary}")

        if recent_history:
            recent = recent_history[-2:]  # last 1 exchange only — keeps input small
            lines = []
            for m in recent:
                role = "User" if m["role"] == "user" else "Bot"
                lines.append(f"{role}: {m['content'][:100]}")
            parts.append("Recent history:\n" + "\n".join(lines))

        if active_context:
            parts.append(f"Active context:\n{active_context}")

        parts.append(f"New message: {message}")
        content = "\n\n".join(parts)

        raw = call_llm(
            messages=[{"role": "user", "content": content}],
            system=_ROUTER_SYSTEM,
            max_tokens=2048,
            language=language,
            step="router",
        )

        parsed = _parse_router_json(raw)
        if not parsed:
            _logger.warning(f"[router] JSON parse failed raw={raw!r}, using fallback")
            return None

        intent = parsed.get("intent", "").strip()
        label = _parse_label(intent) or _parse_label(raw)
        if label is None:
            _logger.warning(f"[router] unknown intent={intent!r}, using fallback")
            return None

        conv_state    = parsed.get("conv_state", "new_query")
        followup_type = parsed.get("followup_type") or None
        confidence    = float(parsed.get("confidence", 0.9))
        reason        = parsed.get("reason", "llm")
        search_query  = parsed.get("search_query", "").strip()

        route = _LABEL_TO_ROUTE[label]
        _logger.info(f"[router] LLM → intent={label} conv_state={conv_state} followup_type={followup_type} conf={confidence:.2f} search_query={search_query!r}")

        return RouteDecision(
            route=route,
            reason=reason,
            confidence=confidence,
            template_key=label,
            conv_state=conv_state,
            followup_type=followup_type if conv_state == "followup" else None,
            search_query=search_query,
        )

    except Exception as exc:
        _logger.warning(f"[router] LLM failed ({exc}), using fallback")
        return None


_TS_KEYWORDS = {
    "th": [
        "เบิกไม่ได้", "เบิกเงินไม่ได้", "ยอด 0", "ยอด0", "0 บาท", "0บาท",
        "แสดง 0", "แสดงผล 0", "ไม่มียอด", "ยอดไม่ขึ้น", "เงินไม่ขึ้น",
        "เบิกไม่ผ่าน", "ทำไมเบิกไม่ได้", "ยังเบิกไม่ได้", "ถึยังเบิก", "ถึคงเบิก",
        "ยอดเบิก", "เป็น 0", "เป็น0",
    ],
    "en": [
        "can't withdraw", "cannot withdraw", "zero balance", "balance 0",
        "withdrawal failed", "not eligible",
    ],
}


def _intent_fallback(intent, message: str = "", language: str = "th") -> RouteDecision:
    """
    Intent/keyword-based fallback when LLM is unavailable.
    Uses intent.value directly (no str()) so str-enum comparison works.
    For 'question' intent, also checks troubleshooting keywords.
    """
    intent_val = intent.value if hasattr(intent, "value") else str(intent)

    # Chitchat / missing-info — intent detection is reliable here
    label = _INTENT_TO_LABEL.get(intent_val)
    if label and label != "faq":
        return RouteDecision(
            route=_LABEL_TO_ROUTE[label],
            reason=f"fallback:intent={intent_val}",
            confidence=0.85,
            template_key=label,
        )

    # For 'question' intent: check troubleshooting keywords before defaulting to FAQ
    if message:
        msg_lower = message.lower()
        lang_key  = "th" if language == "th" else "en"
        for kw in _TS_KEYWORDS.get(lang_key, []):
            if kw in msg_lower:
                return RouteDecision(
                    route=Route.TROUBLESHOOTING,
                    reason=f"fallback:keyword={kw}",
                    confidence=0.8,
                    template_key="troubleshooting_withdrawal",  # safest default
                )

    return RouteDecision(
        route=Route.FAQ,
        reason="fallback:default",
        confidence=0.7,
        template_key="faq",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def decide_route(
    intent,
    message: str,
    language: str,
    tenant_id: str,
    recent_history: list[dict] | None = None,
    active_context: str = "",
    summary: str = "",
) -> RouteDecision:
    """
    LLM classifies the message → route + conv_state + followup_type.
    Falls back to intent-based routing if LLM is unavailable.
    """
    decision = _llm_classify(
        message, language,
        recent_history=recent_history,
        active_context=active_context,
        summary=summary,
    )
    if decision:
        return decision
    return _intent_fallback(intent, message, language)
