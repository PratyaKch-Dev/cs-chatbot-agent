"""
Withdrawal diagnosis rule engine.

6-case rule engine for zero-balance / withdrawal failure scenarios.
Runs domain logic without needing a vector search or LLM for known patterns.

Cases:
    1. BLOCKED        — Account is blocked by admin
    2. BLACKLISTED    — Employee on blacklist
    3. LIMIT_REACHED  — Daily/monthly withdrawal limit exceeded
    4. COOLDOWN       — Too soon since last withdrawal
    5. NOT_ENROLLED   — Employee not enrolled in Salary Hero
    6. SYNC_PENDING   — Payroll not yet synced for current period
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WithdrawalFailureCase(str, Enum):
    BLOCKED = "blocked"
    BLACKLISTED = "blacklisted"
    LIMIT_REACHED = "limit_reached"
    COOLDOWN = "cooldown"
    NOT_ENROLLED = "not_enrolled"
    SYNC_PENDING = "sync_pending"
    UNKNOWN = "unknown"


@dataclass
class WithdrawalDiagnosis:
    case: WithdrawalFailureCase
    employee_id: str
    reason: str
    next_steps: list[str]
    can_self_resolve: bool      # True = user can fix it; False = needs CS/admin


def diagnose_withdrawal_failure(
    employee_id: str,
    employee_status: dict,
    sync_schedule: dict,
) -> WithdrawalDiagnosis:
    """
    Apply rule engine to diagnose why an employee cannot withdraw.

    Args:
        employee_id: The employee's ID
        employee_status: Output from employee_status tool (dict)
        sync_schedule: Output from sync_schedule tool (dict)

    TODO Phase 6: implement all 6 cases.
    """
    raise NotImplementedError("Phase 6")


def _check_blocked(status: dict) -> bool:
    return status.get("status") == "suspended"


def _check_blacklisted(status: dict) -> bool:
    return status.get("blacklisted", False)


def _check_enrolled(status: dict) -> bool:
    return status.get("enrolled", False)


def _check_sync_pending(sync: dict) -> bool:
    return sync.get("sync_status") == "pending"
