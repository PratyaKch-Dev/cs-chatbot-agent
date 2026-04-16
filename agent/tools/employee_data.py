"""LangChain tool — unified employee data (profile, sync, deductions, paycycle, attendance snapshot)."""

import json
import os

from langchain_core.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.employee_data_mock import MockEmployeeDataClient as _Client
else:
    from agent.clients.employee_data_client import EmployeeDataClient as _Client  # type: ignore

_client = _Client()


@tool
def get_employee_data(employee_id: str) -> str:
    """
    Get all core employee data in one call.

    Returns:
      - profile: status, blacklist flag, eligibility
      - sync: last/next sync timestamps and sync_status
      - deductions: salary deduction items for the current period
      - paycycle: current pay cycle start_date and end_date
      - attendance_snapshot: records for the last 7 days (or since paycycle
        start if that is more recent) — sufficient for most diagnostics

    Always call this tool first. If you need attendance history beyond 7 days,
    call get_attendance afterwards with a custom date range (max 30 days,
    configurable via MAX_ATTENDANCE_DAYS).
    """
    try:
        data = _client.get_employee_data(employee_id)
        return json.dumps({
            "profile":             data.profile,
            "sync":                data.sync,
            "deductions":          data.deductions,
            "paycycle":            data.paycycle,
            "attendance_snapshot": data.attendance_snapshot,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
