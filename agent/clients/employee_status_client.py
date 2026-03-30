"""Real employee status API client. Authenticates via Bearer token. Phase 8."""

import os
from agent.clients.base import BaseEmployeeStatusClient, EmployeeStatus

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class EmployeeStatusClient(BaseEmployeeStatusClient):

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_status(self, employee_id: str) -> EmployeeStatus:
        """TODO Phase 8: GET {API_BASE_URL}/employee/status — token identifies the user."""
        raise NotImplementedError("Phase 8 — set USE_MOCK_APIS=true for now")
