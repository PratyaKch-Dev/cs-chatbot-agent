"""Real employee data client — calls GET /api/user/profile with Bearer token."""

import logging
import os

import httpx

from agent.clients.base import BaseEmployeeDataClient, EmployeeData

API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "")
_logger = logging.getLogger("agent.clients.employee_data")


class EmployeeDataClient(BaseEmployeeDataClient):
    def __init__(self, token: str):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_employee_data(self, employee_id: str = "") -> EmployeeData:
        """
        GET {API_BASE_URL}/api/user/profile

        BE derives user_id from the Bearer token — employee_id param is unused
        but kept for interface compatibility with the mock.
        """
        url = f"{API_BASE_URL}/api/user/profile"
        try:
            resp = httpx.get(url, headers=self._headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _logger.error(f"[EmployeeDataClient] HTTP {e.response.status_code}: {url}")
            raise
        except httpx.RequestError as e:
            _logger.error(f"[EmployeeDataClient] request error: {e}")
            raise

        profile = data.get("profile", {})
        resolved_id = profile.get("user_id") or employee_id

        return EmployeeData(
            employee_id=resolved_id,
            remaining_count=int(data.get("remaining_count", 0)),
            profile=profile,
            company=data.get("company", {}),
            bank_account=data.get("bank_account", {}),
            paycycle=data.get("paycycle", {}),
            deductions=data.get("deductions", {}),
            sync=data.get("sync", {}),
        )
