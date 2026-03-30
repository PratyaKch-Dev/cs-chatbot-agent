"""LangChain tool — employee status and eligibility check."""

import os
import json
from langchain.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.employee_status_mock import MockEmployeeStatusClient as _Client
else:
    from agent.clients.employee_status_client import EmployeeStatusClient as _Client  # type: ignore

_client = _Client()


@tool
def get_employee_status(employee_id: str) -> str:
    """
    Get employment status and withdrawal eligibility for an employee.

    Use this tool when the user asks about:
    - Whether they can withdraw salary
    - Account status (active/inactive/suspended)
    - Enrollment status in the Salary Hero programme
    - Blacklist status

    Args:
        employee_id: The employee's ID

    Returns:
        JSON string with employee status details
    """
    result = _client.get_status(employee_id)
    return json.dumps({
        "employee_id": result.employee_id,
        "name": result.name,
        "status": result.status,
        "enrolled": result.enrolled,
        "eligible_for_withdrawal": result.eligible_for_withdrawal,
        "blacklisted": result.blacklisted,
        "enrollment_date": result.enrollment_date,
    }, ensure_ascii=False)
