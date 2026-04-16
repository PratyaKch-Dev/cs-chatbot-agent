"""
Evidence collector and diagnostic context builder.

Parses raw JSON tool outputs from the LangChain troubleshooting agent and
synthesizes them into a structured DiagnosticContext for the answer generator.

Root cause priority order (checked in sequence, first match wins):
    1. blacklisted        — account on blacklist
    2. suspended          — account status = suspended
    3. sync_pending       — payroll sync not yet run
    4. ok                 — no blocking issue found
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
    """
    Render attendance records as inline per-row entries.

    Format (th): 27 มี.ค. 2026  เข้า 08:50 น. / ออก 18:00 น.  ⚠️ remark
    Format (en): 27 Mar 2026  In 08:50 / Out 18:00  ⚠️ remark
    Missing punch shown as —
    """
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
    """Convert '2026-03-20T02:00:00' → '20 มี.ค. 2026 เวลา 02:00 น.' (th) or 'Mar 20, 2026 02:00' (en)."""
    if not iso:
        return "ยังไม่มีกำหนด" if lang == "th" else "Not scheduled"
    try:
        dt = datetime.fromisoformat(iso)
        if lang == "th":
            return f"{dt.day} {_TH_MONTHS[dt.month]} {dt.year} เวลา {dt.strftime('%H:%M')} น."
        else:
            return dt.strftime("%b %d, %Y %H:%M")
    except ValueError:
        return iso

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

RC_BLACKLISTED   = "blacklisted"
RC_SUSPENDED     = "suspended"
RC_INACTIVE      = "status_inactive"   # non-active status (inactive, terminated, etc.)
RC_SYNC_PENDING  = "sync_pending"
RC_OK            = "ok"

_ROOT_CAUSE_LABELS = {
    "th": {
        RC_BLACKLISTED:  "บัญชีถูกระงับการใช้งาน (blacklist)",
        RC_SUSPENDED:    "สถานะบัญชีถูกระงับโดย HR",
        RC_INACTIVE:     "สถานะบัญชีไม่ได้ใช้งาน (ไม่ใช่ active)",
        RC_SYNC_PENDING: "ระบบยังไม่ได้ซิงค์ข้อมูลเงินเดือน",
        RC_OK:           "ไม่พบปัญหาที่ชัดเจน ข้อมูลทุกอย่างปกติ",
    },
    "en": {
        RC_BLACKLISTED:  "Account is blacklisted",
        RC_SUSPENDED:    "Account has been suspended by HR",
        RC_INACTIVE:     "Account status is not active",
        RC_SYNC_PENDING: "Payroll sync is pending — limit not yet updated",
        RC_OK:           "No blocking issue found — all systems normal",
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
    tool_outputs: dict[str, str],   # {tool_name: raw JSON string from LangChain tool}
    language: str = "th",
) -> DiagnosticContext:
    """
    Parse tool outputs and identify the root cause.

    Args:
        employee_id:  Employee being diagnosed
        issue:        Original user complaint
        tool_outputs: Dict of {tool_name: raw JSON string from LangChain tool}
        language:     "th" or "en" for suggested actions

    Returns:
        DiagnosticContext with root_cause and suggested_actions filled in.
    """
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
    """Return the filled answer template for this context, or '' if none found."""
    lang = language if language in ("th", "en") else "th"
    return _build_response_guide(context, lang)


def format_for_llm(context: DiagnosticContext, language: str = "th") -> str:
    """
    Format DiagnosticContext into a structured string for the answer generator.

    Sections:
      1. Summary header  — employee + issue
      2. Root cause      — clear diagnosis
      3. Actions         — what to do next
      4. Detail sections — one block per tool (for follow-up questions)
      5. Follow-ups      — questions the user may want to ask next
    """
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
    emp     = findings.get("get_employee_data", {})
    profile = emp.get("profile", {})
    sync    = emp.get("sync", {})

    if profile.get("blacklisted", False):
        return RC_BLACKLISTED

    status = profile.get("status", "active")
    if status == "suspended":
        return RC_SUSPENDED
    if status not in ("active", "", None):
        return RC_INACTIVE

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
        RC_SYNC_PENDING: [
            "ระบบ sync ทำงานกี่โมง?",
            "ถ้ารอ sync แล้วยังไม่ขึ้น ต้องทำอย่างไร?",
            "ทำไม sync ถึง pending?",
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
    """One block per tool — shown when user asks for more detail."""
    sections = []

    emp        = findings.get("get_employee_data", {})
    profile    = emp.get("profile", {})
    # Prefer explicit get_attendance call (longer range); fall back to snapshot
    attendance = findings.get("get_attendance") or emp.get("attendance_snapshot", {})
    if profile and "error" not in profile:
        if lang == "th":
            sections.append(
                "สถานะบัญชี:\n"
                f"  • ชื่อ: {profile.get('name', '-')}\n"
                f"  • สถานะ: {profile.get('status', '-')}\n"
                f"  • สิทธิ์เบิกเงิน: {'มี' if profile.get('eligible_for_withdrawal') else 'ไม่มี'}\n"
                f"  • Blacklist: {'ใช่ ⚠️' if profile.get('blacklisted') else 'ไม่'}"
            )
        else:
            sections.append(
                "Account Status:\n"
                f"  • Name: {profile.get('name', '-')}\n"
                f"  • Status: {profile.get('status', '-')}\n"
                f"  • Eligible for withdrawal: {profile.get('eligible_for_withdrawal', '-')}\n"
                f"  • Blacklisted: {'Yes ⚠️' if profile.get('blacklisted') else 'No'}"
            )

    sync    = emp.get("sync", {})
    if sync and "error" not in sync:
        status_icon = "⚠️" if sync.get("sync_status") == "pending" else "✅"
        if lang == "th":
            sections.append(
                "การ Sync ข้อมูล:\n"
                f"  • สถานะ: {sync.get('sync_status', '-')} {status_icon}\n"
                f"  • Sync ล่าสุด: {_fmt_datetime(sync.get('last_sync'), 'th')}\n"
                f"  • Sync ถัดไป: {_fmt_datetime(sync.get('next_sync'), 'th')}"
            )
        else:
            sections.append(
                "Sync Schedule:\n"
                f"  • Status: {sync.get('sync_status', '-')} {status_icon}\n"
                f"  • Last sync: {_fmt_datetime(sync.get('last_sync'), 'en')}\n"
                f"  • Next sync: {_fmt_datetime(sync.get('next_sync'), 'en')}"
            )

    if attendance and "error" not in attendance:
        records    = attendance.get("records", [])
        table      = _format_attendance_table(records, lang)
        date_range = ""
        if attendance.get("date_from") and attendance.get("date_to"):
            df = _fmt_date_short(attendance["date_from"], lang)
            dt = _fmt_date_short(attendance["date_to"],   lang)
            date_range = f" ({df} – {dt})"

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

    deductions = emp.get("deductions", {})
    if deductions and "error" not in deductions and deductions.get("items"):
        items = "\n".join(
            f"    - {it['description']}: {it['amount']:,.0f} บาท" if lang == "th"
            else f"    - {it['description']}: {it['amount']:,.0f} THB"
            for it in deductions["items"]
        )
        total = deductions.get("total_deducted", 0)
        if lang == "th":
            sections.append(
                f"การหักเงิน (รวม {total:,.0f} บาท):\n{items}"
            )
        else:
            sections.append(
                f"Deductions (total {total:,.0f} THB):\n{items}"
            )

    return "\n\n".join(sections) if sections else ("  (ไม่มีข้อมูล)" if lang == "th" else "  (no data)")


def _build_response_guide(context: DiagnosticContext, lang: str) -> str:
    """
    Return a pre-filled template where possible.

    Template priority:
      1. Blocking root causes → always use template (blacklisted, suspended, inactive, sync_pending)
      2. ok + deductions      → has_deductions template
      3. ok + remarks         → attendance_remark template
      4. ok + no issues       → normal_active template
      fallback: "" → answer_generator uses LLM
    """
    emp        = context.findings.get("get_employee_data", {})
    profile    = emp.get("profile", {})
    sync       = emp.get("sync", {})
    deductions = emp.get("deductions", {})
    attendance = context.findings.get("get_attendance") or emp.get("attendance_snapshot", {})

    name      = profile.get("name", context.employee_id)
    status    = profile.get("status", "active")
    last_sync = _fmt_datetime(sync.get("last_sync"), lang)
    next_sync = _fmt_datetime(sync.get("next_sync"), lang)

    # Collect remarks
    records = attendance.get("records", []) if attendance else []
    remarks_list = list(dict.fromkeys(r["remarks"] for r in records if r.get("remarks")))
    remarks_text = "\n".join(f"  - {r}" for r in remarks_list) if remarks_list else ""

    # Format deduction items
    ded_items = deductions.get("items", []) if deductions else []
    if lang == "th":
        deductions_text = "\n".join(
            f"  - {it['description']}: {it['amount']:,.0f} บาท" for it in ded_items
        )
    else:
        deductions_text = "\n".join(
            f"  - {it['description']}: {it['amount']:,.0f} THB" for it in ded_items
        )

    attendance_table = _format_attendance_table(records, lang)

    vars_ = {
        "name":             name,
        "employee_id":      context.employee_id,
        "status":           status,
        "last_sync":        last_sync,
        "next_sync":        next_sync,
        "remarks":          remarks_text,
        "deductions":       deductions_text,
        "attendance_table": attendance_table,
    }

    # Pick scenario
    if context.root_cause == RC_BLACKLISTED:
        scenario = "blacklisted"
    elif context.root_cause == RC_SUSPENDED:
        scenario = "suspended"
    elif context.root_cause == RC_INACTIVE:
        scenario = "status_inactive"
    elif context.root_cause == RC_SYNC_PENDING:
        scenario = "sync_pending"
    elif ded_items and not profile.get("eligible_for_withdrawal", True):
        # Deductions are likely why withdrawal is blocked
        scenario = "has_deductions"
    elif remarks_list:
        scenario = "attendance_remark"
    else:
        scenario = "normal_active"

    template = _get_template(scenario, lang)
    if not template:
        return ""   # fall back to LLM

    try:
        return template.format(**vars_).strip()
    except KeyError:
        return template.strip()


def _format_followup_suggestions(root_cause: str, lang: str) -> str:
    questions = _FOLLOWUP_QUESTIONS.get(lang, {}).get(root_cause, [])
    return "\n".join(f"  - {q}" for q in questions)


