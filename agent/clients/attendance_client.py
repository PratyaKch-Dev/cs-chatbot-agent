"""Real attendance API client stub. Phase 8."""

import os

from agent.clients.base import BaseAttendanceClient

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class AttendanceClient(BaseAttendanceClient):
    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> dict:
        """TODO Phase 8: GET {API_BASE_URL}/employee/attendance?from=&to="""
        raise NotImplementedError("Set USE_MOCK_APIS=true for now")
