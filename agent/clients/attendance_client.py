"""Real attendance API client — calls GET /api/v1/user/account/chatbot/attendance with Bearer token."""

import logging
import os

import httpx

from agent.clients.base import BaseAttendanceClient

# Per-environment base URL (shared with employee_data_client).
API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "").rstrip("/")

# App-identity headers the BE auth/middleware expects. Same env vars as
# employee_data_client so a single .env block controls both clients.
_DEVICE_ID   = os.environ.get("API_DEVICE_ID",   "6997E41A-86E8-5003-977C-CE346154EF79")
_APP_VERSION = os.environ.get("API_APP_VERSION", "5.4.4")
_OS_PLATFORM = os.environ.get("API_OS_PLATFORM", "ios")
_USER_AGENT  = os.environ.get("API_USER_AGENT",  "Dev/10102724 CFNetwork/3860.400.51 Darwin/25.3.0")
_VERIFY_SSL  = os.environ.get("API_VERIFY_SSL",  "true").lower() != "false"

_logger = logging.getLogger("agent.clients.attendance")


class AttendanceClient(BaseAttendanceClient):
    def __init__(self, token: str, language: str = "en"):
        self._headers = {
            "Authorization":   f"Bearer {token}",
            "Content-Type":    "application/json",
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": language,
            "language":        language,
            "x-os-platform":   _OS_PLATFORM,
            "x-device-id":     _DEVICE_ID,
            "x-app-version":   _APP_VERSION,
            "User-Agent":      _USER_AGENT,
            "Cache-Control":   "no-cache",
            "Pragma":          "no-cache",
        }

    def get_attendance(
        self, employee_id: str = "", date_from: str = "", date_to: str = ""
    ) -> dict:
        """
        GET {API_BASE_URL}/api/v1/user/account/chatbot/attendance?date_from={date}&date_to={date}

        BE derives user from Bearer token — employee_id is not sent.
        Response shape preserved verbatim from BE:
          {"records": [{"date", "check_in", "check_out", "metadata": {"remark"}}]}
        Downstream code (evidence._ts_section_balance_factors) reads
        metadata.remark directly.
        """
        url = f"{API_BASE_URL}/api/v1/user/account/chatbot/attendance"
        params: dict = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        _logger.info(f"[AttendanceClient] GET {url}  params={params}")
        try:
            resp = httpx.get(url, headers=self._headers, params=params, timeout=10, verify=_VERIFY_SSL)
            _logger.info(
                f"[AttendanceClient] response {resp.status_code} "
                f"({len(resp.content)} bytes, {resp.elapsed.total_seconds()*1000:.0f}ms)"
            )
            resp.raise_for_status()
            data = resp.json()
            raw_records = data.get("records", []) if isinstance(data, dict) else []
            _logger.info(f"[AttendanceClient] returned {len(raw_records)} records")
        except httpx.HTTPStatusError as e:
            _logger.error(
                f"[AttendanceClient] HTTP {e.response.status_code}: {url}  "
                f"body={e.response.text[:300]!r}"
            )
            raise
        except httpx.RequestError as e:
            _logger.error(f"[AttendanceClient] request error: {e}")
            raise

        return {
            "date_from": date_from,
            "date_to":   date_to,
            "records":   raw_records,
        }
