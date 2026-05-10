"""LangChain tool — unified employee data (profile, bank, deductions, sync)."""

import json
import os

from langchain_core.tools import tool
from agent.tools._token import set_token, get_token  # noqa: F401 — re-export set_token for planner


@tool
def get_employee_data(employee_id: str) -> str:
    """
    Get all core employee data in one call.

    Returns:
      - remaining_count: withdrawal eligibility (>0 = can withdraw)
      - profile: status, status_reason, remark, user_id
      - company: name and status
      - bank_account: bank_code, account_no, account_verify
      - sync: sync_type, schedules
      - deductions: total_deducted
      - paycycle: paycycle_status and dates
      - attendance_snapshot: last 7 days (mock only)

    Always call this tool first for withdrawal troubleshooting.
    """
    use_mock = os.environ.get("USE_MOCK_APIS", "true").lower() == "true"
    token = get_token()

    if use_mock or not token:
        from agent.clients.mock.employee_data_mock import MockEmployeeDataClient
        client = MockEmployeeDataClient()
    else:
        from agent.clients.employee_data_client import EmployeeDataClient
        client = EmployeeDataClient(token)

    try:
        data = client.get_employee_data(employee_id)
        return json.dumps({
            "remaining_count":     data.remaining_count,
            "profile":             data.profile,
            "company":             data.company,
            "bank_account":        data.bank_account,
            "sync":                data.sync,
            "deductions":          data.deductions,
            "paycycle":            data.paycycle,
            "attendance_snapshot": data.attendance_snapshot,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
