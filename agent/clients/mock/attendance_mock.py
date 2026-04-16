"""Mock attendance client — reads users.json (second API call, up to MAX_ATTENDANCE_DAYS)."""

import os
from datetime import date, timedelta

from agent.clients.base import BaseAttendanceClient
from agent.clients.mock.data_loader import get_user

# Configurable via environment variable; real API enforces the same cap server-side
MAX_ATTENDANCE_DAYS = int(os.environ.get("MAX_ATTENDANCE_DAYS", "30"))


class MockAttendanceClient(BaseAttendanceClient):
    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> dict:
        # Enforce the configurable max-days cap
        to_date   = date.fromisoformat(date_to)
        from_date = date.fromisoformat(date_from)
        min_from  = to_date - timedelta(days=MAX_ATTENDANCE_DAYS)
        if from_date < min_from:
            from_date = min_from
            date_from = from_date.isoformat()

        raw  = get_user(employee_id)
        data = raw["attendance"]
        records = [
            r for r in data.get("records", [])
            if date_from <= r["date"] <= date_to
        ]
        return {
            "date_from":     date_from,
            "date_to":       date_to,
            "max_days":      MAX_ATTENDANCE_DAYS,
            "total_present": data.get("total_present", 0),
            "total_absent":  data.get("total_absent", 0),
            "total_late":    data.get("total_late", 0),
            "records":       records,
        }
