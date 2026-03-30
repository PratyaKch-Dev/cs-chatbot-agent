"""Mock shift client — looks up employee data from users.json by employee_id."""

from agent.clients.base import BaseShiftClient, ShiftInfo
from agent.clients.mock.data_loader import get_user


class MockShiftClient(BaseShiftClient):
    def get_shift(self, employee_id: str) -> ShiftInfo:
        data = get_user(employee_id)["shift"]
        return ShiftInfo(
            shift_name=data["shift_name"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            days=data["days"],
        )
