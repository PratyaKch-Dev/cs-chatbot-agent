"""
Evidence collector and diagnostic context builder.

Parses raw JSON tool outputs and synthesizes them into a DiagnosticContext
for the answer generator.

Root cause priority order (checked in sequence, first match wins):
    1. blacklisted        — account on blacklist (mock only)
    2. suspended          — account status = suspended
    3. status_inactive    — account status not active
    4. deduction          — total_deducted > 0 and remaining_count = 0
    5. no_bank            — missing bank_code or account_no
    6. bank_unverified    — account_verify != verified
    7. sync_pending       — payroll sync not yet run (mock only)
    8. ok                 — no blocking issue found
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_TH_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

_EN_MONTHS = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_DAY_TH = {
    "SUN": "อาทิตย์", "MON": "จันทร์", "TUE": "อังคาร",
    "WED": "พุธ",     "THU": "พฤหัส",  "FRI": "ศุกร์", "SAT": "เสาร์",
}
_DAY_EN = {
    "SUN": "Sun", "MON": "Mon", "TUE": "Tue",
    "WED": "Wed", "THU": "Thu", "FRI": "Fri", "SAT": "Sat",
}

_FREQ_TH = {"daily": "ทุกวัน", "weekly": "รายสัปดาห์", "monthly": "รายเดือน"}
_FREQ_EN = {"daily": "Daily",  "weekly": "Weekly",      "monthly": "Monthly"}


def _fmt_date_short(date_str: str, lang: str) -> str:
    """Convert 'YYYY-MM-DD' → '27 มี.ค. 2026' (th) or '27 Mar 2026' (en)."""
    try:
        y, m, d = date_str.split("-")
        m_int = int(m)
        if lang == "th":
            return f"{int(d)} {_TH_MONTHS[m_int]} {y}"
        else:
            return f"{int(d)} {_EN_MONTHS[m_int]} {y}"
    except Exception:
        return date_str


def _format_attendance_table(records: list, lang: str) -> str:
    if not records:
        return ""
    dash = "—"
    lines = []
    for r in records:
        date_str = _fmt_date_short(r.get("date", ""), lang)
        ci_raw   = r.get("check_in")
        co_raw   = r.get("check_out")
        remark   = r.get("remarks") or ""
        if lang == "th":
            ci = f"{ci_raw} น." if ci_raw else dash
            co = f"{co_raw} น." if co_raw else dash
            line = f"  {date_str}  เข้า {ci} / ออก {co}"
        else:
            ci = ci_raw or dash
            co = co_raw or dash
            line = f"  {date_str}  In {ci} / Out {co}"
        if remark:
            line += f"  ⚠️ {remark}"
        lines.append(line)
    return "\n".join(lines)


def _fmt_datetime(iso: str | None, lang: str) -> str:
    """Convert ISO datetime → readable local string."""
    if not iso:
        return "ยังไม่มีกำหนด" if lang == "th" else "Not scheduled"
    try:
        # Handle trailing Z
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if lang == "th":
            return f"{dt.day} {_TH_MONTHS[dt.month]} {dt.year} เวลา {dt.strftime('%H:%M')} น."
        else:
            return dt.strftime("%b %d, %Y %H:%M")
    except ValueError:
        return iso


def _format_sync_schedules(schedules: list, lang: str) -> str:
    """Format sync.schedules list for display."""
    if not schedules:
        return "ไม่มีกำหนดการ" if lang == "th" else "No schedule configured"
    lines = []
    for s in schedules:
        freq = s.get("frequency", "")
        days = s.get("days", [])
        time = s.get("time", "")
        if lang == "th":
            freq_str = _FREQ_TH.get(freq, freq)
            days_str = ", ".join(_DAY_TH.get(d, d) for d in days)
            parts = [freq_str]
            if days_str:
                parts.append(f"วัน{days_str}")
            if time:
                parts.append(f"เวลา {time} น.")
            lines.append("  • " + " ".join(parts))
        else:
            freq_str = _FREQ_EN.get(freq, freq)
            days_str = ", ".join(_DAY_EN.get(d, d) for d in days)
            parts = [freq_str]
            if days_str:
                parts.append(f"on {days_str}")
            if time:
                parts.append(f"at {time}")
            lines.append("  • " + " ".join(parts))
    return "\n".join(lines)


import yaml

_TEMPLATES_FILE = Path(__file__).parent.parent / "config" / "answer_templates.yaml"
_templates: dict = {}


def _load_templates() -> dict:
    global _templates
    if not _templates:
        try:
            _templates = yaml.safe_load(_TEMPLATES_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            _templates = {}
    return _templates


def _get_template(scenario: str, lang: str) -> str:
    return _load_templates().get(scenario, {}).get(lang, {}).get("template", "")


# ── Root cause keys ────────────────────────────────────────────────────────────

RC_BLACKLISTED     = "blacklisted"
RC_SUSPENDED       = "suspended"
RC_INACTIVE        = "status_inactive"
RC_DEDUCTION       = "deduction"
RC_NO_BANK         = "no_bank"
RC_BANK_UNVERIFIED = "bank_unverified"
RC_SYNC_PENDING    = "sync_pending"
RC_OK              = "ok"

_ROOT_CAUSE_LABELS = {
    "th": {
        RC_BLACKLISTED:     "บัญชีถูกระงับการใช้งาน (blacklist)",
        RC_SUSPENDED:       "สถานะบัญชีถูกระงับโดย HR",
        RC_INACTIVE:        "สถานะบัญชีไม่ได้ใช้งาน (ไม่ใช่ active)",
        RC_DEDUCTION:       "มียอดหักเงินในรอบนี้ทำให้ยอดเบิกได้เป็น 0",
        RC_NO_BANK:         "ยังไม่ได้ผูกบัญชีธนาคาร",
        RC_BANK_UNVERIFIED: "บัญชีธนาคารยังไม่ได้รับการยืนยัน",
        RC_SYNC_PENDING:    "ระบบยังไม่ได้ซิงค์ข้อมูลเงินเดือน",
        RC_OK:              "ไม่พบปัญหาที่ชัดเจน ข้อมูลทุกอย่างปกติ",
    },
    "en": {
        RC_BLACKLISTED:     "Account is blacklisted",
        RC_SUSPENDED:       "Account has been suspended by HR",
        RC_INACTIVE:        "Account status is not active",
        RC_DEDUCTION:       "Salary deductions have reduced the withdrawable balance to 0",
        RC_NO_BANK:         "No bank account linked",
        RC_BANK_UNVERIFIED: "Bank account is not yet verified",
        RC_SYNC_PENDING:    "Payroll sync is pending — limit not yet updated",
        RC_OK:              "No blocking issue found — all systems normal",
    },
}

_SUGGESTED_ACTIONS = {
    "th": {
        RC_BLACKLISTED: [
            "ติดต่อ HR เพื่อตรวจสอบสาเหตุที่บัญชีถูก blacklist",
            "ไม่สามารถเบิกเงินได้จนกว่า HR จะปลด blacklist",
        ],
        RC_SUSPENDED: [
            "ติดต่อฝ่าย HR เพื่อตรวจสอบสาเหตุและขอให้ปลดระงับบัญชี",
        ],
        RC_INACTIVE: [
            "ติดต่อฝ่าย HR เพื่อตรวจสอบสถานะบัญชีและขอให้อัปเดตเป็น active",
        ],
        RC_DEDUCTION: [
            "ยอดหักเงินลดยอดเบิกได้เหลือ 0 บาท",
            "ติดต่อ HR หากคิดว่ารายการหักเงินไม่ถูกต้อง",
        ],
        RC_NO_BANK: [
            "เพิ่มบัญชีธนาคารในแอป Salary Hero ก่อนเบิกเงิน",
            "ไปที่เมนู 'บัญชีธนาคาร' แล้วกรอกข้อมูลให้ครบ",
        ],
        RC_BANK_UNVERIFIED: [
            "บัญชีธนาคารที่ผูกไว้ยังไม่ผ่านการยืนยัน",
            "ตรวจสอบและยืนยันบัญชีในแอป หรือติดต่อ HR เพื่อขอความช่วยเหลือ",
        ],
        RC_SYNC_PENDING: [
            "รอให้ระบบซิงค์ข้อมูลในรอบถัดไป (ปกติทุกคืน)",
            "แจ้ง HR หรือผู้ดูแลระบบให้ทำการ sync ด่วน หากรอไม่ได้",
        ],
        RC_OK: [
            "ระบบทุกอย่างปกติ หากยังมีปัญหาให้ติดต่อแอดมิน",
        ],
    },
    "en": {
        RC_BLACKLISTED: [
            "Contact HR to investigate why the account is blacklisted",
            "Withdrawal is blocked until HR removes the blacklist flag",
        ],
        RC_SUSPENDED: [
            "Contact HR to investigate the suspension and request reactivation",
        ],
        RC_INACTIVE: [
            "Contact HR to check the account status and update it to active",
        ],
        RC_DEDUCTION: [
            "Salary deductions have brought your withdrawable balance to 0",
            "Contact HR if you believe any deduction is incorrect",
        ],
        RC_NO_BANK: [
            "Add a bank account in the Salary Hero app before withdrawing",
            "Go to 'Bank Account' in the menu and fill in your details",
        ],
        RC_BANK_UNVERIFIED: [
            "Your linked bank account is not yet verified",
            "Complete verification in the app or ask HR for help",
        ],
        RC_SYNC_PENDING: [
            "Wait for the next scheduled sync (normally runs nightly)",
            "If urgent, ask HR or admin to trigger a manual sync",
        ],
        RC_OK: [
            "All systems appear normal — if the issue persists, contact admin",
        ],
    },
}


# ── Dataclass ──────────────────────────────────────────────────────────────────

@dataclass
class DiagnosticContext:
    employee_id: str
    issue: str
    tools_used: list[str]
    findings: dict                   # tool_name → parsed dict
    root_cause: str = RC_OK
    suggested_actions: list[str] = field(default_factory=list)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_diagnostic_context(
    employee_id: str,
    issue: str,
    tool_outputs: dict[str, str],
    language: str = "th",
) -> DiagnosticContext:
    lang = language if language in ("th", "en") else "th"

    findings: dict[str, dict] = {}
    for tool_name, raw in tool_outputs.items():
        try:
            findings[tool_name] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            findings[tool_name] = {"error": f"could not parse output: {str(raw)[:100]}"}

    root_cause = _identify_root_cause(findings)

    return DiagnosticContext(
        employee_id=employee_id,
        issue=issue,
        tools_used=list(tool_outputs.keys()),
        findings=findings,
        root_cause=root_cause,
        suggested_actions=_SUGGESTED_ACTIONS[lang].get(root_cause, []),
    )


def get_filled_template(context: DiagnosticContext, language: str = "th") -> str:
    lang = language if language in ("th", "en") else "th"
    return _build_response_guide(context, lang)


def format_for_llm(context: DiagnosticContext, language: str = "th") -> str:
    lang = language if language in ("th", "en") else "th"
    root_label = _ROOT_CAUSE_LABELS[lang].get(context.root_cause, context.root_cause)
    actions    = "\n".join(f"  - {a}" for a in context.suggested_actions)
    details    = _format_detail_sections(context.findings, lang)
    followups  = _format_followup_suggestions(context.root_cause, lang)

    if lang == "th":
        return (
            f"พนักงาน: {context.employee_id}\n"
            f"ปัญหา: {context.issue}\n"
            f"\n[สาเหตุที่พบ]\n{root_label}\n"
            f"\n[แนวทางแก้ไข]\n{actions}\n"
            f"\n[ข้อมูลรายละเอียด]\n{details}\n"
            f"\n[คำถามที่พนักงานอาจถามเพิ่มเติม]\n{followups}"
        )
    else:
        return (
            f"Employee: {context.employee_id}\n"
            f"Issue: {context.issue}\n"
            f"\n[Root Cause]\n{root_label}\n"
            f"\n[Suggested Actions]\n{actions}\n"
            f"\n[Detail Data]\n{details}\n"
            f"\n[Possible Follow-up Questions]\n{followups}"
        )


# ── Internal helpers ───────────────────────────────────────────────────────────

def _identify_root_cause(findings: dict[str, dict]) -> str:
    """Check findings in priority order and return first matching root cause."""
    emp             = findings.get("get_employee_data", {})
    remaining_count = emp.get("remaining_count", -1)  # -1 = unknown (old mock without mapping)
    profile         = emp.get("profile", {})
    bank            = emp.get("bank_account", {})
    deductions      = emp.get("deductions", {})
    sync            = emp.get("sync", {})

    # If remaining_count is known and positive, user can withdraw — no issue
    if remaining_count > 0:
        return RC_OK

    # Blacklist check (mock backward compat — real API doesn't have this field)
    if profile.get("blacklisted", False):
        return RC_BLACKLISTED

    # Account status is primary logic
    status = profile.get("status", "active")
    if status == "suspended":
        return RC_SUSPENDED
    if status not in ("active", "", None):
        return RC_INACTIVE

    # Deduction check (real API: deductions.total_deducted)
    total_deducted = (deductions or {}).get("total_deducted") or 0
    if total_deducted > 0:
        return RC_DEDUCTION

    # Bank account checks (real API only — bank is {} for mock)
    if bank:
        if not bank.get("bank_code") or not bank.get("account_no"):
            return RC_NO_BANK
        verify = bank.get("account_verify", "verified")
        if verify and verify != "verified":
            return RC_BANK_UNVERIFIED

    # Sync pending (mock backward compat)
    if sync.get("sync_status") == "pending":
        return RC_SYNC_PENDING

    return RC_OK


_FOLLOWUP_QUESTIONS = {
    "th": {
        RC_BLACKLISTED: [
            "ถูก blacklist เพราะอะไร?",
            "ต้องทำอย่างไรให้ถอด blacklist?",
        ],
        RC_SUSPENDED: [
            "บัญชีถูกระงับเพราะอะไร?",
            "ต้องติดต่อ HR คนไหน?",
        ],
        RC_INACTIVE: [
            "สถานะบัญชีไม่ใช่ active เพราะอะไร?",
            "ต้องทำอย่างไรให้กลับมาเบิกเงินได้?",
        ],
        RC_DEDUCTION: [
            "รายการหักเงินมีอะไรบ้าง?",
            "ถ้ารายการหักเงินไม่ถูกต้องต้องทำยังไง?",
        ],
        RC_NO_BANK: [
            "เพิ่มบัญชีธนาคารในแอปยังไง?",
            "ต้องใช้เอกสารอะไรบ้างในการผูกบัญชี?",
        ],
        RC_BANK_UNVERIFIED: [
            "ยืนยันบัญชีธนาคารยังไง?",
            "รอนานแค่ไหนถึงจะยืนยันเสร็จ?",
        ],
        RC_SYNC_PENDING: [
            "ระบบ sync ทำงานกี่โมง?",
            "ถ้ารอ sync แล้วยังไม่ขึ้น ต้องทำอย่างไร?",
        ],
        RC_OK: [
            "ยอดเงินที่เบิกได้คำนวณอย่างไร?",
            "เบิกได้สูงสุดเท่าไหร่?",
            "มีการหักเงินอะไรบ้าง?",
        ],
    },
    "en": {
        RC_BLACKLISTED: [
            "Why was the account blacklisted?",
            "How do I get removed from the blacklist?",
        ],
        RC_SUSPENDED: [
            "Why was the account suspended?",
            "Who in HR should I contact?",
        ],
        RC_INACTIVE: [
            "Why is the account status not active?",
            "What do I need to do to withdraw again?",
        ],
        RC_DEDUCTION: [
            "What deductions have been applied?",
            "How do I dispute a deduction?",
        ],
        RC_NO_BANK: [
            "How do I add a bank account?",
            "What information do I need to link my bank?",
        ],
        RC_BANK_UNVERIFIED: [
            "How do I verify my bank account?",
            "How long does verification take?",
        ],
        RC_SYNC_PENDING: [
            "What time does the sync run?",
            "What if the balance still doesn't update after sync?",
        ],
        RC_OK: [
            "How is the withdrawable amount calculated?",
            "What is the maximum I can withdraw?",
            "What deductions have been applied?",
        ],
    },
}


def _format_detail_sections(findings: dict[str, dict], lang: str) -> str:
    sections = []

    emp      = findings.get("get_employee_data", {})
    profile  = emp.get("profile", {})
    bank     = emp.get("bank_account", {})
    sync     = emp.get("sync", {})
    deduc    = emp.get("deductions", {})
    remaining = emp.get("remaining_count", -1)

    # Attendance: prefer explicit get_attendance, fall back to snapshot (mock)
    attendance = findings.get("get_attendance") or emp.get("attendance_snapshot", {})

    # ── Profile / account status ─────────────────────────────────────────────
    if profile and "error" not in profile:
        status        = profile.get("status", "-")
        status_reason = profile.get("status_reason", "") or ""
        remark        = profile.get("remark", "") or ""
        name          = profile.get("name", "")  # mock only

        if lang == "th":
            lines = ["สถานะบัญชี:"]
            if name:
                lines.append(f"  • ชื่อ: {name}")
            lines.append(f"  • สถานะ: {status}")
            if remaining >= 0:
                lines.append(f"  • ยอดเบิกได้: {'มี' if remaining > 0 else '0 บาท'}")
            if status_reason:
                lines.append(f"  • เหตุผล: {status_reason}")
            if remark:
                lines.append(f"  • หมายเหตุ: {remark}")
            sections.append("\n".join(lines))
        else:
            lines = ["Account Status:"]
            if name:
                lines.append(f"  • Name: {name}")
            lines.append(f"  • Status: {status}")
            if remaining >= 0:
                lines.append(f"  • Withdrawable: {'available' if remaining > 0 else '0 THB'}")
            if status_reason:
                lines.append(f"  • Reason: {status_reason}")
            if remark:
                lines.append(f"  • Remark: {remark}")
            sections.append("\n".join(lines))

    # ── Bank account ─────────────────────────────────────────────────────────
    if bank:
        bank_code  = bank.get("bank_code", "")
        account_no = bank.get("account_no", "")   # already masked by BE
        verify     = bank.get("account_verify", "")
        verify_icon = "✅" if verify == "verified" else "⚠️"
        if lang == "th":
            lines = ["บัญชีธนาคาร:"]
            if bank_code:
                lines.append(f"  • รหัสธนาคาร: {bank_code}")
            if account_no:
                lines.append(f"  • เลขที่บัญชี: {account_no}")
            lines.append(f"  • ยืนยันบัญชี: {verify or '-'} {verify_icon}")
            sections.append("\n".join(lines))
        else:
            lines = ["Bank Account:"]
            if bank_code:
                lines.append(f"  • Bank code: {bank_code}")
            if account_no:
                lines.append(f"  • Account no: {account_no}")
            lines.append(f"  • Verification: {verify or '-'} {verify_icon}")
            sections.append("\n".join(lines))

    # ── Deductions ───────────────────────────────────────────────────────────
    if deduc and "error" not in deduc:
        total = (deduc.get("total_deducted") or 0)
        items = deduc.get("items", [])   # mock may have items list
        updated = deduc.get("deductions_updated_at", "") or ""
        if total > 0 or items:
            if lang == "th":
                lines = [f"การหักเงิน (รวม {total:,.0f} บาท):"]
                for it in items:
                    lines.append(f"  - {it['description']}: {it['amount']:,.0f} บาท")
                if updated:
                    lines.append(f"  อัปเดตล่าสุด: {_fmt_datetime(updated, 'th')}")
            else:
                lines = [f"Deductions (total {total:,.0f} THB):"]
                for it in items:
                    lines.append(f"  - {it['description']}: {it['amount']:,.0f} THB")
                if updated:
                    lines.append(f"  Last updated: {_fmt_datetime(updated, 'en')}")
            sections.append("\n".join(lines))

    # ── Sync schedule ────────────────────────────────────────────────────────
    if sync and "error" not in sync:
        sync_type  = sync.get("sync_type", "")
        schedules  = sync.get("schedules", [])
        # old mock fields
        sync_status = sync.get("sync_status", "")
        last_sync   = sync.get("last_sync")
        next_sync   = sync.get("next_sync")

        if sync_type or schedules or sync_status:
            status_icon = "⚠️" if sync_status == "pending" else ("✅" if sync_status else "")
            if lang == "th":
                lines = ["การ Sync ข้อมูล:"]
                if sync_type:
                    type_label = "อัตโนมัติ" if sync_type == "auto" else "ด้วยตนเอง"
                    lines.append(f"  • รูปแบบ: {type_label}")
                if schedules:
                    lines.append("  • กำหนดการ:")
                    lines.append(_format_sync_schedules(schedules, "th"))
                if sync_status:
                    lines.append(f"  • สถานะ: {sync_status} {status_icon}")
                if last_sync:
                    lines.append(f"  • Sync ล่าสุด: {_fmt_datetime(last_sync, 'th')}")
                if next_sync:
                    lines.append(f"  • Sync ถัดไป: {_fmt_datetime(next_sync, 'th')}")
            else:
                lines = ["Sync Schedule:"]
                if sync_type:
                    lines.append(f"  • Type: {sync_type}")
                if schedules:
                    lines.append("  • Configured schedules:")
                    lines.append(_format_sync_schedules(schedules, "en"))
                if sync_status:
                    lines.append(f"  • Status: {sync_status} {status_icon}")
                if last_sync:
                    lines.append(f"  • Last sync: {_fmt_datetime(last_sync, 'en')}")
                if next_sync:
                    lines.append(f"  • Next sync: {_fmt_datetime(next_sync, 'en')}")
            sections.append("\n".join(lines))

    # ── Attendance (mock / if present) ───────────────────────────────────────
    if attendance and "error" not in attendance:
        records    = attendance.get("records", [])
        table      = _format_attendance_table(records, lang)
        date_range = ""
        if attendance.get("date_from") and attendance.get("date_to"):
            df = _fmt_date_short(attendance["date_from"], lang)
            dt = _fmt_date_short(attendance["date_to"],   lang)
            date_range = f" ({df} – {dt})"

        if records:
            if lang == "th":
                sections.append(
                    f"การเข้างาน{date_range}:\n"
                    f"  • มา {attendance.get('total_present', 0)} วัน, "
                    f"ขาด {attendance.get('total_absent', 0)} วัน, "
                    f"สาย {attendance.get('total_late', 0)} วัน\n\n"
                    f"{table}"
                )
            else:
                sections.append(
                    f"Attendance{date_range}:\n"
                    f"  • Present: {attendance.get('total_present', 0)}, "
                    f"Absent: {attendance.get('total_absent', 0)}, "
                    f"Late: {attendance.get('total_late', 0)}\n\n"
                    f"{table}"
                )

    return "\n\n".join(sections) if sections else ("  (ไม่มีข้อมูล)" if lang == "th" else "  (no data)")


def _build_response_guide(context: DiagnosticContext, lang: str) -> str:
    emp      = context.findings.get("get_employee_data", {})
    profile  = emp.get("profile", {})
    sync     = emp.get("sync", {})
    deduc    = emp.get("deductions", {})
    bank     = emp.get("bank_account", {})
    attendance = context.findings.get("get_attendance") or emp.get("attendance_snapshot", {})

    # Name: prefer profile.name (mock) or fall back to employee_id
    name   = profile.get("name", "") or context.employee_id
    status = profile.get("status", "active")

    # status_reason / remark for inline display
    status_reason_raw = (profile.get("status_reason") or "").strip()
    remark_raw        = (profile.get("remark") or "").strip()
    if lang == "th":
        status_reason_line = f"\nเหตุผล: {status_reason_raw}" if status_reason_raw else ""
        if remark_raw:
            status_reason_line += f"\nหมายเหตุ: {remark_raw}"
    else:
        status_reason_line = f"\nReason: {status_reason_raw}" if status_reason_raw else ""
        if remark_raw:
            status_reason_line += f"\nNote: {remark_raw}"

    # Sync fields — handle both old (mock) and new (real) shapes
    last_sync = _fmt_datetime(sync.get("last_sync"), lang)
    next_sync = _fmt_datetime(sync.get("next_sync"), lang)
    schedules_text = _format_sync_schedules(sync.get("schedules", []), lang)
    sync_type_label = ""
    if sync.get("sync_type"):
        if lang == "th":
            sync_type_label = "อัตโนมัติ" if sync.get("sync_type") == "auto" else "ด้วยตนเอง"
        else:
            sync_type_label = sync.get("sync_type", "")

    # Bank account
    bank_code  = bank.get("bank_code", "")
    account_no = bank.get("account_no", "")  # already masked
    verify     = bank.get("account_verify", "")

    # Deductions
    total_deducted = (deduc.get("total_deducted") or 0)
    ded_items = deduc.get("items", [])  # mock may have items
    if lang == "th":
        deductions_text = "\n".join(
            f"  - {it['description']}: {it['amount']:,.0f} บาท" for it in ded_items
        )
        if not deductions_text and total_deducted:
            deductions_text = f"  ยอดหักรวม: {total_deducted:,.0f} บาท"
    else:
        deductions_text = "\n".join(
            f"  - {it['description']}: {it['amount']:,.0f} THB" for it in ded_items
        )
        if not deductions_text and total_deducted:
            deductions_text = f"  Total deducted: {total_deducted:,.0f} THB"

    # Attendance remarks (mock only)
    records = attendance.get("records", []) if attendance else []
    remarks_list = list(dict.fromkeys(r["remarks"] for r in records if r.get("remarks")))
    remarks_text = "\n".join(f"  - {r}" for r in remarks_list) if remarks_list else ""
    attendance_table = _format_attendance_table(records, lang)

    vars_ = {
        "name":               name,
        "employee_id":        context.employee_id,
        "status":             status,
        "status_reason_line": status_reason_line,
        "last_sync":          last_sync,
        "next_sync":          next_sync,
        "sync_type":          sync_type_label,
        "schedules":          schedules_text,
        "bank_code":          bank_code,
        "account_no":         account_no,
        "account_verify":     verify,
        "total_deducted":     f"{total_deducted:,.0f}",
        "deductions":         deductions_text,
        "remarks":            remarks_text,
        "attendance_table":   attendance_table,
    }

    # Pick scenario
    if context.root_cause == RC_BLACKLISTED:
        scenario = "blacklisted"
    elif context.root_cause == RC_SUSPENDED:
        scenario = "suspended"
    elif context.root_cause == RC_INACTIVE:
        scenario = "status_inactive"
    elif context.root_cause == RC_DEDUCTION:
        scenario = "has_deductions"
    elif context.root_cause == RC_NO_BANK:
        scenario = "no_bank"
    elif context.root_cause == RC_BANK_UNVERIFIED:
        scenario = "bank_unverified"
    elif context.root_cause == RC_SYNC_PENDING:
        scenario = "sync_pending"
    elif remarks_list:
        scenario = "attendance_remark"
    else:
        scenario = "normal_active"

    template = _get_template(scenario, lang)
    if not template:
        return ""

    try:
        return template.format(**vars_).strip()
    except KeyError:
        return template.strip()


def _format_followup_suggestions(root_cause: str, lang: str) -> str:
    questions = _FOLLOWUP_QUESTIONS.get(lang, {}).get(root_cause, [])
    return "\n".join(f"  - {q}" for q in questions)
