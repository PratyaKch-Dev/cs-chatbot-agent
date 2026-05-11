"""Mock balance client — reads from the editable real-shape fixture."""

import logging

from agent.clients.mock import _mock_data

_logger = logging.getLogger("agent.clients.mock.balance")


class MockBalanceClient:
    def get_balance(self, employee_id: str = "") -> dict:
        bal = _mock_data.get_balance()
        amount = bal.get("earned_avaliable_amount")
        if amount is None:
            amount = bal.get("earned_available_amount", 0)
        status = bal.get("status", "ready")
        return {
            "earned_avaliable_amount": amount,
            "earned_available_amount": amount,
            "status":                  status,
        }
