"""LangChain tool — full attendance records for a custom date range (max 30 days, configurable)."""

import json
import os

from langchain_core.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.attendance_mock import MockAttendanceClient as _Client
else:
    from agent.clients.attendance_client import AttendanceClient as _Client  # type: ignore

_client = _Client()


@tool
def get_attendance(employee_id: str, date_from: str, date_to: str) -> str:
    """
    Get full attendance records for a custom date range (YYYY-MM-DD).

    The API enforces a maximum window of MAX_ATTENDANCE_DAYS (default 30, configurable).
    If date_from is further back than allowed, it is clamped automatically.

    Call this tool only when:
      - The attendance_snapshot from get_employee_data is insufficient
        (e.g. user asks about a specific past period or anomalies need more context)
      - You need more than 7 days of history

    Use paycycle.start_date from get_employee_data as date_from for the current cycle.
    """
    try:
        result = _client.get_attendance(employee_id, date_from, date_to)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
