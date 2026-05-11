"""LangChain tool — withdrawable balance + readiness status."""

import json
import os

from langchain_core.tools import tool
from agent.tools._token import get_token


@tool
def get_balance(employee_id: str = "") -> str:
    """
    Get the user's currently withdrawable amount and readiness status.

    Independent of profile/attendance — can run in parallel with them.

    Returns JSON:
      {
        "earned_avaliable_amount": <amount>,
        "earned_available_amount": <amount>,  # alias without BE typo
        "status":                  "ready" | other
      }
    """
    # Same selection rule as the other tools: token presence = real API.
    force_mock = os.environ.get("USE_MOCK_APIS", "false").lower() == "true"
    token = get_token()

    if force_mock or not token:
        from agent.clients.mock.balance_mock import MockBalanceClient
        client = MockBalanceClient()
        try:
            return json.dumps(client.get_balance(employee_id), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    from agent.clients.balance_client import BalanceClient
    client = BalanceClient(token)
    try:
        return json.dumps(client.get_balance(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
