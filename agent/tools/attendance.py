"""LangChain tool — attendance records for a date range."""

import json
import os

from langchain_core.tools import tool
from agent.tools._token import get_token


@tool
def get_attendance(employee_id: str, date_from: str, date_to: str) -> str:
    """
    Get attendance records for a date range (YYYY-MM-DD).

    Use paycycle.start (date part) from get_employee_data as date_from.
    Use today as date_to.

    Call only when remaining_count = 0 and no blocking issue found by Profile API
    (no inactive status, no deduction, no bank issue).

    Returns records with: date, check_in, check_out, remarks (from metadata.remark).
    The API enforces a max window of MAX_ATTENDANCE_DAYS (default 60).
    """
    # Same selection rule as employee_data: token presence = real API.
    # USE_MOCK_APIS=true forces mock even when a token is set (debugging).
    force_mock = os.environ.get("USE_MOCK_APIS", "false").lower() == "true"
    token = get_token()

    if force_mock or not token:
        from agent.clients.mock.attendance_mock import MockAttendanceClient
        client = MockAttendanceClient()
    else:
        from agent.clients.attendance_client import AttendanceClient
        client = AttendanceClient(token)

    try:
        result = client.get_attendance(employee_id, date_from, date_to)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
