"""Mock attendance client.

Reads from the editable real-shape fixture at `_mock_data.py` by default.
Falls back to the legacy `_mock_attendance` block in `users.json` only when
the caller passes a legacy EMP00X employee_id.

Response shape matches real API after normalization:
  metadata.remark → remarks (flattened)
"""

import os
from datetime import date, timedelta

from agent.clients.base import BaseAttendanceClient
from agent.clients.mock.data_loader import get_user, load_mock_users
from agent.clients.mock import _mock_data

MAX_ATTENDANCE_DAYS = int(os.environ.get("MAX_ATTENDANCE_DAYS", "60"))


def _is_legacy_emp_id(employee_id: str) -> bool:
    if not employee_id:
        return False
    try:
        return employee_id in load_mock_users()
    except Exception:
        return False


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

        # Prefer editable fixture; fall back to users.json for legacy ids.
        if _is_legacy_emp_id(employee_id):
            raw  = get_user(employee_id)
            data = raw.get("_mock_attendance") or raw.get("attendance", {})
        else:
            data = _mock_data.get_attendance()

        # Match the real-API shape exactly — keep metadata.remark nested.
        # Legacy fixtures using a flat `remarks` field are lifted into a
        # metadata block so downstream code sees one shape only.
        records = []
        for r in data.get("records", []):
            if date_from <= r["date"] <= (date_to or "9999"):
                metadata = r.get("metadata")
                if metadata is None and "remarks" in r:
                    metadata = {"remark": r.get("remarks")}
                records.append({
                    "date":      r["date"],
                    "check_in":  r.get("check_in"),
                    "check_out": r.get("check_out"),
                    "metadata":  metadata or {"remark": None},
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
