"""
Real attendance API client.

Authenticates via Bearer token. The backend extracts employee identity
from the token — employee_id in method args is ignored.

Phase 8 implementation.
"""

import os
from agent.clients.base import AttendanceSummary, BaseAttendanceClient

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class AttendanceClient(BaseAttendanceClient):

    def __init__(self, token: str):
        """
        Args:
            token: User's auth token (from LINE session context).
                   Passed as Authorization: Bearer {token} header.
                   Backend resolves employee identity from this token.
        """
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> AttendanceSummary:
        """
        TODO Phase 8: implement HTTP call.
        employee_id is ignored — token identifies the user on the backend.

        Example:
            import httpx
            resp = httpx.get(
                f"{API_BASE_URL}/attendance",
                params={"date_from": date_from, "date_to": date_to},
                headers=self.headers,
            )
            resp.raise_for_status()
            return _parse(resp.json())
        """
        raise NotImplementedError("Phase 8 — set USE_MOCK_APIS=true for now")
