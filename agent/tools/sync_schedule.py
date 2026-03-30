"""LangChain tool — payroll sync schedule lookup."""

import os
import json
from langchain.tools import tool

if os.environ.get("USE_MOCK_APIS", "true").lower() == "true":
    from agent.clients.mock.sync_schedule_mock import MockSyncScheduleClient as _Client
else:
    from agent.clients.sync_schedule_client import SyncScheduleClient as _Client  # type: ignore

_client = _Client()


@tool
def get_sync_schedule(employee_id: str) -> str:
    """
    Get the payroll sync status and schedule for an employee.

    Use this tool when the user asks about:
    - When their salary data was last synced
    - Why their withdrawal limit hasn't updated
    - Next sync time
    - Sync failures

    Args:
        employee_id: The employee's ID

    Returns:
        JSON string with sync schedule details
    """
    result = _client.get_sync_schedule(employee_id)
    return json.dumps({
        "employee_id": result.employee_id,
        "last_sync": result.last_sync,
        "next_sync": result.next_sync,
        "sync_status": result.sync_status,
    }, ensure_ascii=False)
