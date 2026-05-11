"""Real balance/withdraw API client — calls GET /api/v1/user/ewa/balance/withdraw with Bearer token."""

import logging
import os

import httpx

# Per-environment base URL (shared with profile + attendance clients).
API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "").rstrip("/")

# Same app-identity headers as the other clients.
_DEVICE_ID   = os.environ.get("API_DEVICE_ID",   "6997E41A-86E8-5003-977C-CE346154EF79")
_APP_VERSION = os.environ.get("API_APP_VERSION", "5.4.4")
_OS_PLATFORM = os.environ.get("API_OS_PLATFORM", "ios")
_USER_AGENT  = os.environ.get("API_USER_AGENT",  "Dev/10102724 CFNetwork/3860.400.51 Darwin/25.3.0")
_VERIFY_SSL  = os.environ.get("API_VERIFY_SSL",  "true").lower() != "false"

_logger = logging.getLogger("agent.clients.balance")


class BalanceClient:
    """
    Fetches the user's withdrawable balance.

    Endpoint: GET {API_BASE_URL}/api/v1/user/ewa/balance/withdraw
    Auth:     Authorization: Bearer {access_token}

    Response contract:
      {
        "earned_avaliable_amount": <int|float>,   # (note BE typo "avaliable")
        "status":                  "ready" | other
      }

    BE derives the user from the Bearer token — no employee_id is sent.
    This call is independent of the Profile and Attendance calls, so it can
    run in parallel with them.
    """

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

    def get_balance(self) -> dict:
        """
        Return the BE response dict.

        Normalises the response shape so downstream code can read both the
        BE field name (`earned_avaliable_amount`, with the typo) and a
        corrected alias (`earned_available_amount`).
        """
        url = f"{API_BASE_URL}/api/v1/user/ewa/balance/withdraw"
        _logger.info(f"[BalanceClient] GET {url}")
        try:
            resp = httpx.get(url, headers=self._headers, timeout=10, verify=_VERIFY_SSL)
            _logger.info(
                f"[BalanceClient] response {resp.status_code} "
                f"({len(resp.content)} bytes, {resp.elapsed.total_seconds()*1000:.0f}ms)"
            )
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            _logger.error(
                f"[BalanceClient] HTTP {e.response.status_code}: {url}  "
                f"body={e.response.text[:300]!r}"
            )
            raise
        except httpx.RequestError as e:
            _logger.error(f"[BalanceClient] request error: {e}")
            raise

        # Normalise: keep both spellings so callers don't have to guess.
        amount = data.get("earned_avaliable_amount")
        if amount is None:
            amount = data.get("earned_available_amount", 0)
        status = data.get("status", "")
        _logger.info(f"[BalanceClient] amount={amount} status={status!r}")
        return {
            "earned_avaliable_amount": amount,
            "earned_available_amount": amount,   # alias without BE typo
            "status":                  status,
        }
