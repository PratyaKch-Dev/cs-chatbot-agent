"""LangChain tool — salary deduction lookup."""

import os
import json
from langchain.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.deduction_mock import MockDeductionClient as _Client
else:
    from agent.clients.deduction_client import DeductionClient as _Client  # type: ignore

_client = _Client()


@tool
def get_salary_deductions(employee_id: str, period: str) -> str:
    """
    Get salary deduction breakdown for an employee in a given pay period.

    Use this tool when the user asks about:
    - Why their salary is less than expected
    - What was deducted and why
    - Deduction amounts and reasons

    Args:
        employee_id: The employee's ID
        period: Pay period in YYYY-MM format (e.g. "2026-03")

    Returns:
        JSON string with deduction items and total
    """
    result = _client.get_deductions(employee_id, period)
    return json.dumps({
        "employee_id": result.employee_id,
        "period": result.period,
        "total_deducted": result.total_deducted,
        "items": [
            {
                "type": item.type,
                "amount": item.amount,
                "description": item.description,
                "date": item.date,
            }
            for item in result.items
        ],
    }, ensure_ascii=False)
