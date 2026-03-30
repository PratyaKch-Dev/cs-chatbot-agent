"""Real sync schedule API client. Authenticates via Bearer token. Phase 8."""

import os
from agent.clients.base import BaseSyncScheduleClient, SyncSchedule

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")


class SyncScheduleClient(BaseSyncScheduleClient):

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_sync_schedule(self, employee_id: str) -> SyncSchedule:
        """TODO Phase 8: GET {API_BASE_URL}/sync/schedule — token identifies the user."""
        raise NotImplementedError("Phase 8 — set USE_MOCK_APIS=true for now")
