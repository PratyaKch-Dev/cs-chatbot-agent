"""LangChain tool — shift schedule lookup."""

import os
import json
from langchain.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.shift_mock import MockShiftClient as _Client
else:
    from agent.clients.shift_client import ShiftClient as _Client  # type: ignore

_client = _Client()


@tool
def get_shift_schedule(employee_id: str) -> str:
    """
    Get the current shift schedule for an employee.

    Use this tool when the user asks about:
    - Work hours / shift times
    - Which days they are supposed to work
    - Shift assignment issues

    Args:
        employee_id: The employee's ID

    Returns:
        JSON string with shift details
    """
    result = _client.get_shift(employee_id)
    return json.dumps({
        "shift_name": result.shift_name,
        "start_time": result.start_time,
        "end_time": result.end_time,
        "days": result.days,
    }, ensure_ascii=False)
