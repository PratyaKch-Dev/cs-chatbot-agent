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
        md       = r.get("metadata") or {}
        remark   = (md.get("remark") if isinstance(md, dict) else None) or r.get("remarks") or ""
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


def _check_paycycle_window(paycycle: dict) -> str | None:
    """
    Defensive paycycle date check.
    Returns RC_OUTSIDE_PAYCYCLE / RC_PAST_CUTOFF when today fails either gate,
    or None when the dates are missing/invalid (let other checks decide).
    """
    if not isinstance(paycycle, dict):
        return None
    start, end, cutoff = paycycle.get("start"), paycycle.get("end"), paycycle.get("cutoff")
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        def _p(s: str | None):
            if not s:
                return None
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        start_dt, end_dt, cutoff_dt = _p(start), _p(end), _p(cutoff)
        # Outside window — today before start or after end.
        if (start_dt and now < start_dt) or (end_dt and now > end_dt):
            return "outside_paycycle_window"
        # Past cutoff — within window but deadline has elapsed.
        if cutoff_dt and now >= cutoff_dt:
            return "past_cutoff"
    except Exception:
        return None
    return None


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
_templates_mtime: float = 0.0   # last-seen file mtime → reload on change


def _load_templates() -> dict:
    """
    Read answer_templates.yaml, caching the parsed dict.

    Hot reload: re-reads the file whenever its mtime changes, so editing
    YAML during a running session takes effect on the NEXT message (no
    bot restart needed). Falls back to the previous cache on parse error.
    """
    global _templates, _templates_mtime
    try:
        mtime = _TEMPLATES_FILE.stat().st_mtime
    except OSError:
        return _templates  # file missing — keep whatever we had

    if _templates and mtime == _templates_mtime:
        return _templates

    try:
        parsed = yaml.safe_load(_TEMPLATES_FILE.read_text(encoding="utf-8")) or {}
        _templates       = parsed
        _templates_mtime = mtime
    except Exception:
        # Bad YAML mid-edit: keep last good cache so the bot stays up.
        pass
    return _templates


def _get_template(scenario: str, lang: str) -> str:
    return _load_templates().get(scenario, {}).get(lang, {}).get("template", "")


# ── Root cause keys ────────────────────────────────────────────────────────────

RC_BLACKLISTED     = "blacklisted"        # deprecated — BE no longer returns this
RC_SUSPENDED       = "suspended"          # deprecated — BE no longer returns this
RC_INACTIVE        = "status_inactive"    # profile.status == "inactive"
RC_HAS_REMARK      = "has_remark"         # profile.metadata.remark truthy (status="active")
RC_PAYCYCLE_INACTIVE     = "paycycle_inactive"        # paycycle.paycycle_status == "inactive"
RC_OUTSIDE_PAYCYCLE      = "outside_paycycle_window"  # today not in [paycycle.start, paycycle.end]
RC_PAST_CUTOFF           = "past_cutoff"              # today >= paycycle.cutoff
RC_DATA_OUTDATED   = "data_outdated"      # employee_data_status == "outdated"
RC_DEDUCTION       = "has_deductions"     # deductions.total_deducted > 0
RC_NO_BANK         = "no_bank"            # missing bank_code or account_no
RC_BANK_UNVERIFIED = "bank_unverified"    # deprecated — verify state no longer blocks
RC_SYNC_PENDING    = "sync_pending"       # mock-only (legacy)
RC_OK              = "ok"

_ROOT_CAUSE_LABELS = {
    "th": {
        RC_BLACKLISTED:       "บัญชีถูกระงับการใช้งาน (blacklist)",
        RC_SUSPENDED:         "สถานะบัญชีถูกระงับโดย HR",
        RC_INACTIVE:          "สถานะบัญชีไม่ได้ใช้งาน (inactive)",
        RC_HAS_REMARK:        "พบหมายเหตุจาก HR บนข้อมูลผู้ใช้ของคุณ",
        RC_PAYCYCLE_INACTIVE: "รอบจ่ายค่าจ้างของบริษัทยังไม่เปิดใช้งาน",
        RC_OUTSIDE_PAYCYCLE:  "ขณะนี้อยู่นอกช่วงวันที่อนุญาตให้เบิกของรอบนี้",
        RC_PAST_CUTOFF:       "เลยกำหนดเวลาเบิกของรอบนี้แล้ว",
        RC_DATA_OUTDATED:     "ข้อมูลของคุณยังไม่ได้รับการอัปเดตจากบริษัท",
        RC_DEDUCTION:         "มียอดหักเงินในรอบนี้ทำให้ยอดเบิกได้เป็น 0",
        RC_NO_BANK:           "ยังไม่ได้ผูกบัญชีธนาคาร",
        RC_BANK_UNVERIFIED:   "บัญชีธนาคารยังไม่ได้รับการยืนยัน",
        RC_SYNC_PENDING:      "ระบบยังไม่ได้ซิงค์ข้อมูลเงินเดือน",
        RC_OK:                "ไม่พบปัญหาที่ชัดเจน ข้อมูลทุกอย่างปกติ",
    },
    "en": {
        RC_BLACKLISTED:       "Account is blacklisted",
        RC_SUSPENDED:         "Account has been suspended by HR",
        RC_INACTIVE:          "Account status is inactive",
        RC_HAS_REMARK:        "HR has left a remark on your profile",
        RC_PAYCYCLE_INACTIVE: "The company's pay cycle is not currently active",
        RC_OUTSIDE_PAYCYCLE:  "Today is outside the allowed withdrawal window for this pay cycle",
        RC_PAST_CUTOFF:       "The withdrawal cutoff for this pay cycle has passed",
        RC_DATA_OUTDATED:     "Your data hasn't been synced from the company yet",
        RC_DEDUCTION:         "Salary deductions have reduced the withdrawable balance to 0",
        RC_NO_BANK:           "No bank account linked",
        RC_BANK_UNVERIFIED:   "Bank account is not yet verified",
        RC_SYNC_PENDING:      "Payroll sync is pending — limit not yet updated",
        RC_OK:                "No blocking issue found — all systems normal",
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
        RC_HAS_REMARK: [
            "ข้อมูลของคุณมีหมายเหตุจาก HR — ติดต่อ HR เพื่อขอรายละเอียดเพิ่มเติม",
        ],
        RC_PAYCYCLE_INACTIVE: [
            "รอบจ่ายค่าจ้างยังไม่เปิดใช้งาน — รอให้บริษัทเริ่มรอบใหม่",
            "หากเร่งด่วน ติดต่อฝ่าย HR ของบริษัทเพื่อตรวจสอบ",
        ],
        RC_OUTSIDE_PAYCYCLE: [
            "ขณะนี้อยู่นอกช่วงวันที่อนุญาตให้เบิก — รอรอบจ่ายค่าจ้างถัดไป",
        ],
        RC_PAST_CUTOFF: [
            "เลยกำหนดเวลาเบิกของรอบนี้แล้ว — รอรอบจ่ายค่าจ้างถัดไป",
        ],
        RC_DATA_OUTDATED: [
            "ข้อมูลของคุณยังไม่ได้รับการอัปเดตล่าสุดจากบริษัท",
            "ระบบจะอัปเดตอัตโนมัติในรอบถัดไป — รอ 24 ชั่วโมงแล้วลองใหม่",
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
        RC_HAS_REMARK: [
            "HR has left a remark on your profile — contact HR for more details",
        ],
        RC_PAYCYCLE_INACTIVE: [
            "The pay cycle isn't active yet — wait for the company to open the next one",
            "If urgent, contact your HR team to investigate",
        ],
        RC_OUTSIDE_PAYCYCLE: [
            "Today is outside the allowed withdrawal window — wait for the next pay cycle to open",
        ],
        RC_PAST_CUTOFF: [
            "Today's withdrawal cutoff has passed — wait for the next pay cycle",
        ],
        RC_DATA_OUTDATED: [
            "Your data hasn't been synced from the company yet",
            "The system auto-syncs on a schedule — wait 24 hours and try again",
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
    """
    Check findings in priority order and return first matching root cause.
    See planning/USER_PROFILE_API_SPEC.md for the canonical decision tree.

    Priority (when remaining_count == 0):
      1. status == "inactive"              → status_inactive
      2. metadata.remark truthy            → has_remark
      3. paycycle_status == "inactive"     → paycycle_inactive
      4. employee_data_status == outdated  → data_outdated
      5. total_deducted > 0                → has_deductions
      6. missing bank_code OR account_no   → no_bank
      7. otherwise                         → ok  (→ Attendance API next)
    """
    emp                  = findings.get("get_employee_data", {})
    remaining_count      = emp.get("remaining_count", -1)   # -1 = unknown
    profile              = emp.get("profile", {})
    bank                 = emp.get("bank_account", {})
    paycycle             = emp.get("paycycle", {})
    deductions           = emp.get("deductions", {})
    sync                 = emp.get("sync", {})
    # employee_data_status lives in `paycycle` per the real API, but the
    # employee_data tool also hoists it to the top level. Accept both.
    employee_data_status = (
        emp.get("employee_data_status")
        or (paycycle or {}).get("employee_data_status")
        or "up_to_date"
    )

    # If remaining_count is known and positive, user can withdraw — no issue
    if remaining_count > 0:
        return RC_OK

    # Legacy mock support — blacklist as a top-level boolean. Real API removed.
    if profile.get("blacklisted", False):
        return RC_BLACKLISTED

    # 1. Account status (primary, binary: active | inactive)
    status = profile.get("status", "active")
    if status == "inactive":
        return RC_INACTIVE
    # Legacy mock support
    if status == "suspended":
        return RC_SUSPENDED

    # 2. HR-provided remark on the profile (status is active but HR left a note)
    metadata = profile.get("metadata") or {}
    remark   = metadata.get("remark") if isinstance(metadata, dict) else None
    # Also accept the legacy flat `profile.remark` shape used by old mocks
    if not remark:
        remark = profile.get("remark")
    if remark:   # truthy → non-empty string
        return RC_HAS_REMARK

    # 3a. Paycycle inactive — paycycle_status is binary: "active" | "inactive".
    if (paycycle or {}).get("paycycle_status") == "inactive":
        return RC_PAYCYCLE_INACTIVE

    # 3b. Today outside the paycycle window [start, end].
    # 3c. Today past the paycycle cutoff (within window but past deadline).
    # Both checks defensively guard against the BE leaving paycycle_status="active"
    # while the window has actually closed or the cutoff has passed.
    pc_check = _check_paycycle_window(paycycle)
    if pc_check:
        return pc_check

    # 4. HRIS data not yet synced — balance shown may be stale
    if employee_data_status == "outdated":
        return RC_DATA_OUTDATED

    # 5. Deductions consumed the withdrawable balance
    total_deducted = (deductions or {}).get("total_deducted") or 0
    if total_deducted > 0:
        return RC_DEDUCTION

    # 6. Bank existence — both bank_code AND account_no must be present.
    # account_verify is NOT checked: per current BE rules, verification state
    # does not block withdrawal.
    if bank:
        if not bank.get("bank_code") or not bank.get("account_no"):
            return RC_NO_BANK

    # Legacy mock support — sync_status field used by users.json fixtures
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


def _build_withdrawal_diagnostic(context: DiagnosticContext, lang: str) -> str:
    """
    3-section diagnostic for the troubleshooting_withdrawal flow.
    Always shown when balance + attendance findings are present.

      §1  Balance header (ยอดเบิกได้ตอนนี้)
      §2  Eligibility checklist  (✓ ผ่าน / ✗ list)
      §3  "Why balance is 0 / not updated" — deductions + full attendance table
    """
    emp = context.findings.get("get_employee_data", {})
    bal = context.findings.get("get_balance", {})
    att = context.findings.get("get_attendance") or emp.get("attendance_snapshot", {})

    # Detect API failures FIRST — if profile failed, the rest of the diagnostic
    # is meaningless (no eligibility data, no paycycle, no name).
    error_section = _ts_section_api_errors(emp, bal, att, lang)
    if error_section and _ts_is_profile_failed(emp):
        return error_section

    sec1 = _ts_section_balance(bal, lang)
    sec2 = _ts_section_eligibility(emp, lang)
    sec3 = _ts_section_balance_factors(emp, att, lang)
    sec4 = _ts_section_suggestions(emp, bal, att, lang)

    parts = [s for s in [sec1, sec2, sec3, sec4] if s]
    if error_section:
        # Profile is OK but balance/attendance failed — render what we have
        # and surface the partial failure at the bottom so the user knows
        # why a section is missing.
        parts.append(error_section)
    return "\n\n".join(parts)


def _ts_is_profile_failed(emp: dict) -> bool:
    """True if get_employee_data couldn't return real data."""
    if not emp:
        return True
    if "error" in emp:
        return True
    # No profile / paycycle dicts → nothing usable downstream
    return not (emp.get("profile") or emp.get("paycycle"))


def _ts_error_reason(finding: dict, lang: str) -> str:
    """Map a tool's error blob to a short user-facing reason.

    HTTP 401 is special-cased as "token expired" since that's the failure
    mode users can actually act on (re-login). Everything else falls back
    to a generic message with the error type.
    """
    s_api = (_ts_strings(lang).get("api_errors") or {})
    raw = (finding or {}).get("error", "")
    if not raw:
        return ""
    if "401" in raw or "Unauthorized" in raw or "Unauthenticated" in raw:
        return s_api.get("token_expired", "Token expired — please sign in again")
    # Strip very long URLs / stack-y bits to a short prefix
    short = raw.split("\n")[0][:80]
    return short


def _ts_section_api_errors(emp: dict, bal: dict, att: dict, lang: str) -> str:
    """Build the ⚠️ warning section when any of the 3 calls failed.

    Returns empty string when everything succeeded. Caller decides whether
    to render it standalone (profile failed → only show this) or appended
    (partial failure → show data + warning)."""
    s_api = (_ts_strings(lang).get("api_errors") or {})
    if not s_api:
        return ""

    lines: list[str] = []
    profile_err = _ts_error_reason(emp, lang) if (emp and "error" in emp) else ""
    balance_err = _ts_error_reason(bal, lang) if (bal and "error" in bal) else ""
    attend_err  = _ts_error_reason(att, lang) if (att and "error" in att) else ""

    # If any 401 is detected on any call, treat as global session-expired.
    token_msg = s_api.get("token_expired", "")
    any_401 = any(token_msg and (e == token_msg) for e in (profile_err, balance_err, attend_err))
    if any_401:
        return "\n".join([
            s_api.get("header", "⚠️ Data not available"),
            token_msg,
            s_api.get("contact_support", ""),
        ]).rstrip()

    if profile_err:
        lines.append(s_api.get("profile_fail", "Profile failed: {reason}").format(reason=profile_err))
    if balance_err:
        lines.append(s_api.get("balance_fail", "Balance failed: {reason}").format(reason=balance_err))
    if attend_err:
        lines.append(s_api.get("attendance_fail", "Attendance failed: {reason}").format(reason=attend_err))

    if not lines:
        return ""
    return "\n".join([s_api.get("header", "⚠️ Data not available"), *lines, s_api.get("contact_support", "")]).rstrip()


def _ts_is_all_clear(emp: dict, bal: dict, att: dict) -> bool:
    """True when nothing in the diagnostic indicates a problem.

    All six eligibility checks must pass, balance.status must be 'ready' (or
    blank), there must be no deductions this cycle, and every attendance
    record must have both punches and no remark. Any API error disqualifies
    "all clear" — we don't want to tell a user "everything is normal" when
    we couldn't actually load their data.
    """
    if any((d or {}).get("error") for d in (emp, bal, att)):
        return False
    profile  = emp.get("profile", {}) or {}
    bank     = emp.get("bank_account", {}) or {}
    paycycle = emp.get("paycycle", {}) or {}

    if profile.get("status", "active") != "active":
        return False
    md = profile.get("metadata") or {}
    remark = (md.get("remark") if isinstance(md, dict) else None) or profile.get("remark")
    if remark:
        return False
    if not (bank.get("bank_code") and bank.get("account_no")):
        return False
    if paycycle.get("paycycle_status", "active") == "inactive":
        return False
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        def _p(v):
            return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None
        s_dt, e_dt, c_dt = _p(paycycle.get("start")), _p(paycycle.get("end")), _p(paycycle.get("cutoff"))
        if (s_dt and now < s_dt) or (e_dt and now > e_dt) or (c_dt and now >= c_dt):
            return False
    except Exception:
        pass
    if (paycycle.get("employee_data_status") or "up_to_date") != "up_to_date":
        return False

    status = (bal or {}).get("status", "")
    if status and status != "ready":
        return False

    try:
        total = float((emp.get("deductions") or {}).get("total_deducted") or 0)
    except (TypeError, ValueError):
        total = 0.0
    if total > 0:
        return False

    for r in (att or {}).get("records", []) or []:
        ci = (r.get("check_in") or "")[:5]
        co = (r.get("check_out") or "")[:5]
        rmd = r.get("metadata") or {}
        rrem = (rmd.get("remark") if isinstance(rmd, dict) else None) or r.get("remarks")
        if (not ci) or (not co) or rrem:
            return False

    return True


def _ts_section_suggestions(emp: dict, bal: dict, att: dict, lang: str) -> str:
    """Unified §4 "คำแนะนำ:" section — collects every action line in priority
    order. For the happy path, renders the all-clear closing instead."""
    s = _ts_strings(lang)
    header = s.get("suggestions_header") or "คำแนะนำ:"

    if _ts_is_all_clear(emp, bal, att):
        body = (s.get("all_clear_message") or "").rstrip()
        return f"{header}\n{body}" if body else ""

    chk = s.get("checks", {}) or {}
    profile  = emp.get("profile", {}) or {}
    bank     = emp.get("bank_account", {}) or {}
    paycycle = emp.get("paycycle", {}) or {}

    suggestions: list[str] = []

    # §1 — balance status (not_ready / pending …)
    status = (bal or {}).get("status", "")
    if status and status != "ready":
        action = (s.get("balance_status_actions", {}) or {}).get(status)
        if action:
            suggestions.append(action)

    # §2 — eligibility failures, in display order
    if profile.get("status", "active") != "active":
        suggestions.append((chk.get("active", {}) or {}).get("action", ""))
    md = profile.get("metadata") or {}
    remark = (md.get("remark") if isinstance(md, dict) else None) or profile.get("remark")
    if remark:
        suggestions.append((chk.get("no_remark", {}) or {}).get("action", ""))
    if not (bank.get("bank_code") and bank.get("account_no")):
        suggestions.append((chk.get("bank", {}) or {}).get("action", ""))
    if paycycle.get("paycycle_status", "active") == "inactive":
        suggestions.append((chk.get("paycycle_active", {}) or {}).get("action", ""))
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        def _p(v):
            return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None
        s_dt, e_dt, c_dt = _p(paycycle.get("start")), _p(paycycle.get("end")), _p(paycycle.get("cutoff"))
        if (s_dt and now < s_dt) or (e_dt and now > e_dt) or (c_dt and now >= c_dt):
            suggestions.append((chk.get("in_window", {}) or {}).get("action", ""))
    except Exception:
        pass
    if (paycycle.get("employee_data_status") or "up_to_date") != "up_to_date":
        suggestions.append((chk.get("fresh_data", {}) or {}).get("action", ""))

    # §3 — deductions present
    try:
        total = float((emp.get("deductions") or {}).get("total_deducted") or 0)
    except (TypeError, ValueError):
        total = 0.0
    if total > 0:
        suggestions.append(s.get("deduction_action", ""))

    # §3 — attendance issues. We surface two distinct suggestions:
    #   1. action_attendance_remark — names the specific date(s) that carry
    #      a remark (HR note, system flag, late, etc.). The remark text is
    #      free-form, so we don't quote it; we just point the user at HR.
    #   2. action_missing_check — fires for rows that are missing a punch
    #      WITHOUT a remark (a missing punch with a remark is already
    #      explained by the remark itself — covered by #1).
    remark_dates: list[str] = []
    missing_only = False
    for r in (att or {}).get("records", []) or []:
        ci = (r.get("check_in") or "")[:5]
        co = (r.get("check_out") or "")[:5]
        rmd = r.get("metadata") or {}
        rrem = (rmd.get("remark") if isinstance(rmd, dict) else None) or r.get("remarks")
        if rrem:
            remark_dates.append(_fmt_date_short(r.get("date", ""), lang))
        elif (not ci) or (not co):
            missing_only = True

    if remark_dates:
        tmpl = s.get("action_attendance_remark", "")
        if tmpl:
            suggestions.append(tmpl.format(dates=", ".join(remark_dates)))
    if missing_only:
        suggestions.append(s.get("action_missing_check", ""))

    # Dedupe while preserving order; strip empties.
    seen: set[str] = set()
    ordered: list[str] = []
    for line in suggestions:
        line = (line or "").strip()
        if line and line not in seen:
            seen.add(line)
            ordered.append(line)

    if not ordered:
        return ""

    return "\n".join([header, *ordered])


def _ts_strings(lang: str) -> dict:
    """Load the withdrawal_diagnostic string block from answer_templates.yaml."""
    cfg = _load_templates().get("withdrawal_diagnostic", {})
    return cfg.get(lang) or cfg.get("th") or {}


def _translate_status(raw: str, lang: str) -> str:
    """Map BE status strings ('active', 'outdated', ...) to Thai/EN copy."""
    if not raw:
        return ""
    if lang != "th":
        return raw  # English: BE already uses readable English values
    table = _ts_strings(lang).get("status_th", {}) or {}
    return table.get(raw, raw)   # unknown values fall back to the raw string


def _ts_section_balance(bal: dict, lang: str) -> str:
    s = _ts_strings(lang)
    amount = bal.get("earned_avaliable_amount")
    if amount is None:
        amount = bal.get("earned_available_amount", 0) or 0
    try:
        amount_fmt = f"{float(amount):,.0f}"
    except (TypeError, ValueError):
        amount_fmt = "0"
    status = bal.get("status", "")
    line = f"{s.get('balance_header', '')}: {amount_fmt} {s.get('balance_unit', '')}"
    if status and status != "ready":
        line += f" ({s.get('balance_status_label', 'status')}: {_translate_status(status, lang)})"
    return line


def _ts_section_eligibility(emp: dict, lang: str) -> str:
    s     = _ts_strings(lang)
    chk   = s.get("checks", {}) or {}

    profile  = emp.get("profile", {}) or {}
    bank     = emp.get("bank_account", {}) or {}
    paycycle = emp.get("paycycle", {}) or {}

    # 1. status (binary: active | inactive)
    is_active = profile.get("status", "active") == "active"

    # 2. no HR remark
    md = profile.get("metadata") or {}
    remark = (md.get("remark") if isinstance(md, dict) else None) or profile.get("remark")
    no_remark = not remark

    # 3. bank linked
    has_bank = bool(bank.get("bank_code") and bank.get("account_no"))

    # 4. paycycle active
    pc_active = paycycle.get("paycycle_status", "active") != "inactive"

    # 5. today within [start, end] AND before cutoff
    in_window = True
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        def _p(v):
            return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None
        s_dt, e_dt, c_dt = _p(paycycle.get("start")), _p(paycycle.get("end")), _p(paycycle.get("cutoff"))
        if (s_dt and now < s_dt) or (e_dt and now > e_dt) or (c_dt and now >= c_dt):
            in_window = False
    except Exception:
        pass

    # 6. data fresh
    eds = paycycle.get("employee_data_status") or "up_to_date"
    fresh = eds == "up_to_date"

    def _msg(key: str, side: str, **fmt) -> str:
        cfg = chk.get(key, {}) or {}
        tmpl = cfg.get(side, "")
        try:
            return tmpl.format(**fmt) if fmt else tmpl
        except (KeyError, IndexError):
            return tmpl

    def _action(key: str) -> str:
        return (chk.get(key, {}) or {}).get("action", "")

    checks = [
        # (passed, pass_label, fail_label, action_for_fail)
        (is_active,  _msg("active",          "pass"),  _msg("active",          "fail"),                      _action("active")),
        (no_remark,  _msg("no_remark",       "pass"),  _msg("no_remark",       "fail", remark=remark or ""), _action("no_remark")),
        (has_bank,   _msg("bank",            "pass"),  _msg("bank",            "fail"),                      _action("bank")),
        (pc_active,  _msg("paycycle_active", "pass"),  _msg("paycycle_active", "fail"),                      _action("paycycle_active")),
        (in_window,  _msg("in_window",       "pass"),  _msg("in_window",       "fail"),                      _action("in_window")),
        (fresh,      _msg("fresh_data",      "pass"),  _msg("fresh_data",      "fail"),                      _action("fresh_data")),
    ]

    if all(passed for passed, _, _, _ in checks):
        return s.get("eligibility_pass", "")

    # Data only — actions are consolidated into §4 (คำแนะนำ:).
    lines = [s.get("eligibility_header", "")]
    for passed, _, fail_label, _action in checks:
        if not passed:
            lines.append(f"✗ {fail_label}")
    return "\n".join(lines)


def _ts_section_balance_factors(emp: dict, att: dict, lang: str) -> str:
    s = _ts_strings(lang)

    deductions = emp.get("deductions") or {}
    try:
        total = float(deductions.get("total_deducted") or 0)
    except (TypeError, ValueError):
        total = 0.0
    updated_at = (deductions.get("deductions_updated_at") or "")[:10]
    updated_str = _fmt_date_short(updated_at, lang) if updated_at else ""

    records = (att or {}).get("records", []) or []
    max_show = 31
    missing_label = s.get("attendance_missing", "(missing)")

    # Remark hint — if any record carries a remark (HR note, system flag,
    # "ลืม check in", etc.), prepend a one-line cue under the §3 header so
    # the user understands why the balance may not be updating. The remark
    # text itself is rendered next to its row in the attendance table below.
    def _rec_remark(r):
        md = r.get("metadata") or {}
        return (md.get("remark") if isinstance(md, dict) else None) or r.get("remarks")
    has_any_remark = any(_rec_remark(r) for r in records)

    out: list[str] = [s.get("factors_header", "")]
    if has_any_remark:
        hint = s.get("attendance_remark_hint", "")
        if hint:
            out.append(hint)
    out.append("")

    deduct_line = f"{s.get('deduction_label', '')}: {total:,.0f} {s.get('balance_unit', '')}"
    if updated_str:
        deduct_line += " " + s.get("deduction_updated", "({date})").format(date=updated_str)
    out.append(deduct_line)

    if records:
        out.append("")
        out.append(s.get("attendance_header", ""))
        for r in records[:max_show]:
            d_str = _fmt_date_short(r.get("date", ""), lang)
            ci = (r.get("check_in") or "")[:5]
            co = (r.get("check_out") or "")[:5]
            md = r.get("metadata") or {}
            remark = md.get("remark") if isinstance(md, dict) else None
            if not remark:
                remark = r.get("remarks")
            missing = (not ci) or (not co)
            marker = "✗" if (missing or remark) else "✓"
            ci_disp = ci if ci else missing_label
            co_disp = co if co else missing_label
            # Pad single-digit Thai day so the times line up
            d_padded = d_str.rjust(len(d_str) + 1) if d_str and d_str[0].isdigit() and (len(d_str.split()[0]) == 1) else d_str
            line = f"{marker} {d_padded}  {ci_disp} - {co_disp}"
            if remark:
                line += f"   \"{remark}\""
            out.append(line)
        if len(records) > max_show:
            out.append(s.get("more_records_suffix", "(+{n} more)").format(n=len(records) - max_show))

    return "\n".join(out)


def _build_response_guide(context: DiagnosticContext, lang: str) -> str:
    # Withdrawal flow → use the 3-section composite diagnostic (Option B layout).
    # Triggered when the planner called both employee_data + balance (the agent
    # only does this for troubleshooting_withdrawal).
    if "get_balance" in context.findings:
        return _build_withdrawal_diagnostic(context, lang)

    emp      = context.findings.get("get_employee_data", {})
    profile  = emp.get("profile", {})
    sync     = emp.get("sync", {})
    deduc    = emp.get("deductions", {})
    bank     = emp.get("bank_account", {})
    attendance = context.findings.get("get_attendance") or emp.get("attendance_snapshot", {})

    # Name: prefer profile.name (mock) or fall back to employee_id
    # Display name preference:
    #   1. profile.name (legacy mock fixtures only — real API doesn't return this)
    #   2. polite generic "คุณ" / "you" — keeps templates clean when no real
    #      name is available. We deliberately avoid using `context.employee_id`
    #      because that's the raw value typed into Gradio (e.g. "mock_user")
    #      and would leak into user-facing text.
    name = profile.get("name") or ("คุณ" if lang == "th" else "you")
    status = profile.get("status", "active")

    # Remark — single source: profile.metadata.remark (real API), with a
    # fallback to legacy flat fields for mock backwards-compat.
    metadata     = profile.get("metadata") or {}
    remark_raw   = ""
    if isinstance(metadata, dict):
        remark_raw = (metadata.get("remark") or "").strip()
    if not remark_raw:
        # Legacy mock shapes: profile.remark or profile.status_reason
        remark_raw = (profile.get("remark") or profile.get("status_reason") or "").strip()

    if remark_raw:
        remark_line = f"\nหมายเหตุจาก HR: {remark_raw}" if lang == "th" else f"\nHR remark: {remark_raw}"
    else:
        remark_line = ""

    # Kept for backwards-compat with templates that still reference {status_reason_line}.
    status_reason_line = remark_line

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

    # Attendance remarks (real BE: metadata.remark; legacy mocks: remarks)
    records = attendance.get("records", []) if attendance else []
    def _rec_remark(r):
        md = r.get("metadata") or {}
        return (md.get("remark") if isinstance(md, dict) else None) or r.get("remarks")
    remarks_list = list(dict.fromkeys(rm for rm in (_rec_remark(r) for r in records) if rm))
    remarks_text = "\n".join(f"  - {r}" for r in remarks_list) if remarks_list else ""
    attendance_table = _format_attendance_table(records, lang)

    # Balance (informational only — never drives root_cause).
    balance_raw = context.findings.get("get_balance") or {}
    earned_amount   = balance_raw.get("earned_avaliable_amount")
    if earned_amount is None:
        earned_amount = balance_raw.get("earned_available_amount", 0) or 0
    try:
        earned_amount_fmt = f"{float(earned_amount):,.0f}"
    except (TypeError, ValueError):
        earned_amount_fmt = "0"
    balance_status = balance_raw.get("status", "")
    if earned_amount or balance_status:
        if lang == "th":
            balance_line = f"ยอดเบิกได้ตอนนี้: {earned_amount_fmt} บาท"
            if balance_status and balance_status != "ready":
                balance_line += f" (สถานะ: {balance_status})"
        else:
            balance_line = f"Withdrawable now: {earned_amount_fmt} THB"
            if balance_status and balance_status != "ready":
                balance_line += f" (status: {balance_status})"
        # Trailing blank line so it sits as a header above the main template.
        balance_line += "\n\n"
    else:
        balance_line = ""

    # next_start_line: shown in paycycle_inactive / outside_paycycle_window /
    # past_cutoff templates so the user knows when withdrawals will reopen.
    paycycle_block = emp.get("paycycle", {}) or {}
    next_start_iso = paycycle_block.get("next_start") or ""
    next_start_pretty = _fmt_date_short(next_start_iso[:10], lang) if next_start_iso else ""
    if next_start_pretty:
        if lang == "th":
            next_start_line = f"\n(รอบถัดไปเริ่ม {next_start_pretty})"
        else:
            next_start_line = f"\n(Next cycle opens {next_start_pretty})"
    else:
        next_start_line = ""

    # sync_line: shown in data_outdated when schedules are configured
    if sync_type_label and schedules_text:
        if lang == "th":
            sync_line = f"\n\nรอบ sync: {sync_type_label}\n{schedules_text}"
        else:
            sync_line = f"\n\nSync schedule: {sync_type_label}\n{schedules_text}"
    else:
        sync_line = ""

    vars_ = {
        "name":               name,
        "employee_id":        context.employee_id,
        "status":             status,
        "remark":             remark_raw,
        "remark_line":        remark_line,
        "status_reason_line": status_reason_line,   # legacy alias of remark_line
        "sync_line":          sync_line,
        "next_start_line":    next_start_line,
        "next_start_date":    next_start_pretty,
        "balance_line":       balance_line,
        "earned_amount":      earned_amount_fmt,
        "balance_status":     balance_status,
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

    # Pick scenario — root_cause keys map 1:1 to scenario keys in
    # config/answer_templates.yaml. Order mirrors the decision tree priority.
    if context.root_cause == RC_INACTIVE:
        scenario = "status_inactive"
    elif context.root_cause == RC_HAS_REMARK:
        scenario = "has_remark"
    elif context.root_cause == RC_PAYCYCLE_INACTIVE:
        scenario = "paycycle_inactive"
    elif context.root_cause == RC_OUTSIDE_PAYCYCLE:
        scenario = "outside_paycycle_window"
    elif context.root_cause == RC_PAST_CUTOFF:
        scenario = "past_cutoff"
    elif context.root_cause == RC_DATA_OUTDATED:
        scenario = "data_outdated"
    elif context.root_cause == RC_DEDUCTION:
        scenario = "has_deductions"
    elif context.root_cause == RC_NO_BANK:
        scenario = "no_bank"
    # Legacy / deprecated — kept so any mock or older code that emits these
    # keys still resolves to a template instead of falling through.
    elif context.root_cause == RC_BLACKLISTED:
        scenario = "blacklisted"
    elif context.root_cause == RC_SUSPENDED:
        scenario = "suspended"
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
