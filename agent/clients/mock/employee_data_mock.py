"""Mock unified employee data client — reads users.json (first API call)."""

from datetime import date, timedelta

from agent.clients.base import BaseEmployeeDataClient, EmployeeData
from agent.clients.mock.data_loader import get_user

_SNAPSHOT_DAYS = 7


class MockEmployeeDataClient(BaseEmployeeDataClient):
    def get_employee_data(self, employee_id: str) -> EmployeeData:
        raw = get_user(employee_id)
        paycycle = raw.get("paycycle", {})

        # Attendance snapshot: max(paycycle_start, today − 7 days) → today
        today = date.today()
        fallback_from = today - timedelta(days=_SNAPSHOT_DAYS)
        paycycle_start = paycycle.get("start_date")
        if paycycle_start:
            snapshot_from = max(date.fromisoformat(paycycle_start), fallback_from)
        else:
            snapshot_from = fallback_from

        date_from = snapshot_from.isoformat()
        date_to   = today.isoformat()

        att = raw.get("attendance", {})
        records = [
            r for r in att.get("records", [])
            if date_from <= r["date"] <= date_to
        ]
        attendance_snapshot = {
            "date_from":     date_from,
            "date_to":       date_to,
            "total_present": att.get("total_present", 0),
            "total_absent":  att.get("total_absent", 0),
            "total_late":    att.get("total_late", 0),
            "records":       records,
        }

        return EmployeeData(
            employee_id=employee_id,
            profile=raw["profile"],
            sync=raw["sync"],
            deductions=raw["deductions"],
            paycycle=paycycle,
            attendance_snapshot=attendance_snapshot,
        )
