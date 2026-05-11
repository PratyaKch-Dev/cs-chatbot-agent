"""Mock unified employee data client.

Reads from the editable fixture at `agent/clients/mock/_mock_data.py` (the
real-API-shape mock you can flip fields on without restarting).
Falls back to the legacy `users.json` keyed by employee_id when the caller
passes one of the historical mock ids (EMP00X) — needed by old test scripts.
"""

from datetime import date, timedelta, datetime

from agent.clients.base import BaseEmployeeDataClient, EmployeeData
from agent.clients.mock.data_loader import get_user, load_mock_users
from agent.clients.mock import _mock_data

_SNAPSHOT_DAYS = 7


def _is_legacy_emp_id(employee_id: str) -> bool:
    """True when employee_id matches an EMP00X key in the legacy users.json."""
    if not employee_id:
        return False
    try:
        return employee_id in load_mock_users()
    except Exception:
        return False


def _parse_iso_date(iso: str | None) -> date | None:
    """Extract date from ISO datetime string like '2026-04-01T17:00:00.000Z'."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(iso[:10])
        except Exception:
            return None


class MockEmployeeDataClient(BaseEmployeeDataClient):
    def get_employee_data(self, employee_id: str = "") -> EmployeeData:
        # Prefer the editable real-shape fixture unless the caller is using a
        # legacy EMP00X id (those still resolve from users.json for back-compat).
        if _is_legacy_emp_id(employee_id):
            raw = get_user(employee_id)
        else:
            raw = _mock_data.get_profile()

        paycycle     = raw.get("paycycle", {})
        att_raw      = raw.get("_mock_attendance", {})

        # Attendance snapshot: max(paycycle_start, today − 7 days) → today
        today         = date.today()
        fallback_from = today - timedelta(days=_SNAPSHOT_DAYS)
        paycycle_start = _parse_iso_date(paycycle.get("start"))
        snapshot_from  = max(paycycle_start, fallback_from) if paycycle_start else fallback_from

        date_from = snapshot_from.isoformat()
        date_to   = today.isoformat()

        records = [
            r for r in att_raw.get("records", [])
            if date_from <= r["date"] <= date_to
        ]
        attendance_snapshot = {
            "date_from":     date_from,
            "date_to":       date_to,
            "total_present": att_raw.get("total_present", 0),
            "total_absent":  att_raw.get("total_absent", 0),
            "total_late":    att_raw.get("total_late", 0),
            "records":       records,
        }

        # For sync_pending mock scenario: promote _mock_sync_status → sync.sync_status
        sync = dict(raw.get("sync", {}))
        if "_mock_sync_status" in sync:
            sync["sync_status"] = sync.pop("_mock_sync_status")

        return EmployeeData(
            employee_id=raw["profile"].get("user_id", employee_id),
            remaining_count=raw.get("remaining_count", 0),
            profile=raw.get("profile", {}),
            company=raw.get("company", {}),
            bank_account=raw.get("bank_account", {}),
            paycycle=paycycle,
            deductions=raw.get("deductions", {}),
            sync=sync,
            attendance_snapshot=attendance_snapshot,
        )
