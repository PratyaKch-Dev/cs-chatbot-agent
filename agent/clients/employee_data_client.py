"""Real employee data client — calls GET /api/v1/user/account/chatbot/profile with Bearer token."""

import logging
import os

import httpx

from agent.clients.base import BaseEmployeeDataClient, EmployeeData

# Per-environment base URL. Set in .env per environment:
#   INTERNAL_API_BASE_URL=https://apiv2-dev.salary-hero.com    (dev)
#   INTERNAL_API_BASE_URL=https://apiv2-staging.salary-hero.com (staging)
#   INTERNAL_API_BASE_URL=https://api.salary-hero.com          (production)
API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "").rstrip("/")

# App-identity headers required by the BE auth/middleware. Configurable via env
# so each deployment (dev / staging / prod / test) can identify itself.
_DEVICE_ID    = os.environ.get("API_DEVICE_ID",    "6997E41A-86E8-5003-977C-CE346154EF79")
_APP_VERSION  = os.environ.get("API_APP_VERSION",  "5.4.4")
_OS_PLATFORM  = os.environ.get("API_OS_PLATFORM",  "ios")
_USER_AGENT   = os.environ.get("API_USER_AGENT",   "Dev/10102724 CFNetwork/3860.400.51 Darwin/25.3.0")
# Allow disabling TLS verification for local dev / staging behind self-signed
# certs. NEVER enable this in production.
_VERIFY_SSL   = os.environ.get("API_VERIFY_SSL",   "true").lower() != "false"

_logger = logging.getLogger("agent.clients.employee_data")


class EmployeeDataClient(BaseEmployeeDataClient):
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

    def get_employee_data(self, employee_id: str = "") -> EmployeeData:
        """
        GET {API_BASE_URL}/api/v1/user/account/chatbot/profile

        BE derives user_id from the Bearer token — employee_id param is unused
        but kept for interface compatibility with the mock.
        """
        url = f"{API_BASE_URL}/api/v1/user/account/chatbot/profile"
        _logger.info(f"[EmployeeDataClient] GET {url}")
        try:
            resp = httpx.get(url, headers=self._headers, timeout=10, verify=_VERIFY_SSL)
            _logger.info(
                f"[EmployeeDataClient] response {resp.status_code} "
                f"({len(resp.content)} bytes, {resp.elapsed.total_seconds()*1000:.0f}ms)"
            )
            resp.raise_for_status()
            data = resp.json()
            # Log a redacted snapshot so the user can verify what came back.
            _logger.info(
                "[EmployeeDataClient] payload keys: %s",
                sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            if isinstance(data, dict):
                prof = data.get("profile", {})
                _logger.info(
                    "[EmployeeDataClient] profile: user_id=%r status=%r remaining_count=%s",
                    prof.get("user_id"), prof.get("status"), data.get("remaining_count"),
                )
        except httpx.HTTPStatusError as e:
            _logger.error(
                f"[EmployeeDataClient] HTTP {e.response.status_code}: {url}  "
                f"body={e.response.text[:300]!r}"
            )
            raise
        except httpx.RequestError as e:
            _logger.error(f"[EmployeeDataClient] request error: {e}")
            raise

        profile = data.get("profile", {})
        resolved_id = profile.get("user_id") or employee_id

        # `employee_data_status` lives inside `paycycle` per the real API
        # (not at the top level). Read from there with a top-level fallback
        # for backwards compat with older mocks.
        paycycle = data.get("paycycle", {}) or {}
        eds = (
            paycycle.get("employee_data_status")
            or data.get("employee_data_status")
            or "up_to_date"
        )

        return EmployeeData(
            employee_id=resolved_id,
            remaining_count=int(data.get("remaining_count", 0)),
            employee_data_status=eds,
            profile=profile,
            company=data.get("company", {}),
            bank_account=data.get("bank_account", {}),
            paycycle=data.get("paycycle", {}),
            deductions=data.get("deductions", {}),
            sync=data.get("sync", {}),
        )
