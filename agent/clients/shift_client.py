"""Real shift API client. Authenticates via Bearer token. Phase 8."""

import os
from agent.clients.base import BaseShiftClient, ShiftInfo

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class ShiftClient(BaseShiftClient):

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_shift(self, employee_id: str) -> ShiftInfo:
        """TODO Phase 8: GET {API_BASE_URL}/shift — token identifies the user."""
        raise NotImplementedError("Phase 8 — set USE_MOCK_APIS=true for now")
