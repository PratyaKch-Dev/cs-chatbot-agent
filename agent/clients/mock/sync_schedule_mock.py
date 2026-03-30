"""Mock sync schedule client — looks up employee data from users.json by employee_id."""

from agent.clients.base import BaseSyncScheduleClient, SyncSchedule
from agent.clients.mock.data_loader import get_user


class MockSyncScheduleClient(BaseSyncScheduleClient):
    def get_sync_schedule(self, employee_id: str) -> SyncSchedule:
        data = get_user(employee_id)["sync"]
        return SyncSchedule(
            employee_id=employee_id,
            last_sync=data["last_sync"],
            next_sync=data["next_sync"],
            sync_status=data["sync_status"],
        )
