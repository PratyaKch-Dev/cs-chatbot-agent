"""Mock attendance client — reads _mock_attendance from users.json.

Response shape matches real API after normalization:
  metadata.remark → remarks (flattened)
"""

import os
from datetime import date, timedelta

from agent.clients.base import BaseAttendanceClient
from agent.clients.mock.data_loader import get_user

MAX_ATTENDANCE_DAYS = int(os.environ.get("MAX_ATTENDANCE_DAYS", "60"))


class MockAttendanceClient(BaseAttendanceClient):
    def get_attendance(
        self, employee_id: str = "", date_from: str = "", date_to: str = ""
    ) -> dict:
        # Enforce max-days cap
        to_date   = date.fromisoformat(date_to)   if date_to   else date.today()
        from_date = date.fromisoformat(date_from)  if date_from else to_date - timedelta(days=7)
        min_from  = to_date - timedelta(days=MAX_ATTENDANCE_DAYS)
        if from_date < min_from:
            from_date = min_from
            date_from = from_date.isoformat()

        raw  = get_user(employee_id)
        data = raw.get("_mock_attendance") or raw.get("attendance", {})

        # Normalize: metadata.remark or legacy remarks → remarks
        records = []
        for r in data.get("records", []):
            if date_from <= r["date"] <= (date_to or "9999"):
                metadata = r.get("metadata") or {}
                remark   = metadata.get("remark") or r.get("remarks")
                records.append({
                    "date":      r["date"],
                    "check_in":  r.get("check_in"),
                    "check_out": r.get("check_out"),
                    "remarks":   remark,
                })

        return {
            "date_from":     date_from,
            "date_to":       date_to,
            "max_days":      MAX_ATTENDANCE_DAYS,
            "total_present": data.get("total_present", 0),
            "total_absent":  data.get("total_absent", 0),
            "total_late":    data.get("total_late", 0),
            "records":       records,
        }
