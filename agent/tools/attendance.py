"""LangChain tool — attendance records lookup."""

import os
import json
from langchain.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.attendance_mock import MockAttendanceClient as _Client
else:
    from agent.clients.attendance_client import AttendanceClient as _Client  # type: ignore

_client = _Client()


@tool
def get_attendance_records(employee_id: str, date_from: str, date_to: str) -> str:
    """
    Get attendance records for an employee within a date range.

    Use this tool when the user asks about:
    - Attendance history (present/absent/late)
    - Why salary was deducted due to attendance
    - Number of absent or late days

    Args:
        employee_id: The employee's ID
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format

    Returns:
        JSON string with attendance records and summary
    """
    result = _client.get_attendance(employee_id, date_from, date_to)
    return json.dumps({
        "employee_id": result.employee_id,
        "total_present": result.total_present,
        "total_absent": result.total_absent,
        "total_late": result.total_late,
        "records": [
            {
                "date": r.date,
                "check_in": r.check_in,
                "check_out": r.check_out,
                "status": r.status,
            }
            for r in result.records
        ],
    }, ensure_ascii=False)
