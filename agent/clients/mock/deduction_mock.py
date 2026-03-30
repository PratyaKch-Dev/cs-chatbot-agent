"""Mock deduction client — looks up employee data from users.json by employee_id."""

from agent.clients.base import BaseDeductionClient, DeductionItem, DeductionSummary
from agent.clients.mock.data_loader import get_user


class MockDeductionClient(BaseDeductionClient):
    def get_deductions(self, employee_id: str, period: str) -> DeductionSummary:
        data = get_user(employee_id)["deductions"]
        return DeductionSummary(
            employee_id=employee_id,
            period=period,
            items=[
                DeductionItem(
                    type=item["type"],
                    amount=item["amount"],
                    description=item["description"],
                    date=item["date"],
                )
                for item in data["items"]
            ],
            total_deducted=data["total_deducted"],
        )
