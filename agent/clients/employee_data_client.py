"""Real unified employee data client stub. Phase 8."""

import os

from agent.clients.base import BaseEmployeeDataClient, EmployeeData

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class EmployeeDataClient(BaseEmployeeDataClient):
    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_employee_data(self, employee_id: str) -> EmployeeData:
        """
        TODO Phase 8: GET {API_BASE_URL}/employee/data
        Returns profile, sync, deductions, paycycle, and attendance_snapshot
        (last 7 days or since paycycle start, whichever is more recent).
        """
        raise NotImplementedError("Set USE_MOCK_APIS=true for now")
