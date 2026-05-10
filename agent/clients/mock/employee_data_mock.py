"""Mock unified employee data client — reads users.json (new API structure)."""

from datetime import date, timedelta, datetime

from agent.clients.base import BaseEmployeeDataClient, EmployeeData
from agent.clients.mock.data_loader import get_user

_SNAPSHOT_DAYS = 7


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
        raw = get_user(employee_id)

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
