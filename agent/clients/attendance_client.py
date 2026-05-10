"""Real attendance API client — calls GET /api/user/attendance with Bearer token."""

import logging
import os

import httpx

from agent.clients.base import BaseAttendanceClient

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")
_logger = logging.getLogger("agent.clients.attendance")


class AttendanceClient(BaseAttendanceClient):
    def __init__(self, token: str):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_attendance(
        self, employee_id: str = "", date_from: str = "", date_to: str = ""
    ) -> dict:
        """
        GET {API_BASE_URL}/api/user/attendance?date_from={date}&date_to={date}

        BE derives user from Bearer token — employee_id is not sent.
        Response: {"records": [{"date", "check_in", "check_out", "metadata": {"remark"}}]}
        Normalizes metadata.remark → remarks for uniform downstream handling.
        """
        url = f"{API_BASE_URL}/api/user/attendance"
        params: dict = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        try:
            resp = httpx.get(url, headers=self._headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _logger.error(f"[AttendanceClient] HTTP {e.response.status_code}: {url}")
            raise
        except httpx.RequestError as e:
            _logger.error(f"[AttendanceClient] request error: {e}")
            raise

        records = _normalize_records(data.get("records", []))
        return {
            "date_from": date_from,
            "date_to":   date_to,
            "records":   records,
        }


def _normalize_records(raw_records: list) -> list:
    """Flatten metadata.remark → remarks so evidence module has a uniform shape."""
    normalized = []
    for r in raw_records:
        metadata = r.get("metadata") or {}
        normalized.append({
            "date":      r.get("date", ""),
            "check_in":  r.get("check_in"),
            "check_out": r.get("check_out"),
            "remarks":   metadata.get("remark"),
        })
    return normalized
