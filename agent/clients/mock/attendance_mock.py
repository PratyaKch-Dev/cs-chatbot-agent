"""Mock attendance client — looks up employee data from users.json by employee_id."""

from agent.clients.base import AttendanceRecord, AttendanceSummary, BaseAttendanceClient
from agent.clients.mock.data_loader import get_user


class MockAttendanceClient(BaseAttendanceClient):
    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> AttendanceSummary:
        data = get_user(employee_id)["attendance"]
        return AttendanceSummary(
            employee_id=employee_id,
            records=[
                AttendanceRecord(
                    date=r["date"],
                    check_in=r["check_in"],
                    check_out=r["check_out"],
                    status=r["status"],
                )
                for r in data["records"]
            ],
            total_present=data["total_present"],
            total_absent=data["total_absent"],
            total_late=data["total_late"],
        )
