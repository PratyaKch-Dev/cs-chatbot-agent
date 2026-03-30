"""Real deduction API client. Authenticates via Bearer token. Phase 8."""

import os
from agent.clients.base import BaseDeductionClient, DeductionSummary

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class DeductionClient(BaseDeductionClient):

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_deductions(self, employee_id: str, period: str) -> DeductionSummary:
        """TODO Phase 8: GET {API_BASE_URL}/deductions?period={period} — token identifies the user."""
        raise NotImplementedError("Phase 8 — set USE_MOCK_APIS=true for now")
