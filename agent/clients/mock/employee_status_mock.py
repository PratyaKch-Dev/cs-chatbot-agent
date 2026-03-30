"""Mock employee status client — looks up employee data from users.json by employee_id."""

from agent.clients.base import BaseEmployeeStatusClient, EmployeeStatus
from agent.clients.mock.data_loader import get_user


class MockEmployeeStatusClient(BaseEmployeeStatusClient):
    def get_status(self, employee_id: str) -> EmployeeStatus:
        data = get_user(employee_id)["profile"]
        return EmployeeStatus(
            employee_id=data["employee_id"],
            name=data["name"],
            status=data["status"],
            enrolled=data["enrolled"],
            eligible_for_withdrawal=data["eligible_for_withdrawal"],
            blacklisted=data["blacklisted"],
            enrollment_date=data["enrollment_date"],
        )
