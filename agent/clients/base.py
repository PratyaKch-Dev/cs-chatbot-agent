"""
Abstract base classes for all HR API clients.

Two modes:
    Mock  — pass employee_id per method call, data loaded from users.json
    Real  — pass token at init, backend extracts employee_id from token
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ── Shared data models ────────────────────────────────────────────────────────

@dataclass
class AttendanceRecord:
    date: str
    check_in: Optional[str]
    check_out: Optional[str]
    remarks: Optional[str] = None


@dataclass
class AttendanceSummary:
    employee_id: str
    records: list[AttendanceRecord]
    total_present: int
    total_absent: int
    total_late: int


@dataclass
class DeductionItem:
    type: str
    amount: float
    description: str
    date: str


@dataclass
class DeductionSummary:
    employee_id: str
    period: str
    items: list[DeductionItem]
    total_deducted: float


@dataclass
class EmployeeStatus:
    employee_id: str
    name: str
    status: str                 # active | inactive | suspended
    eligible_for_withdrawal: bool
    blacklisted: bool
    enrollment_date: Optional[str]


@dataclass
class SyncSchedule:
    employee_id: str
    last_sync: Optional[str]
    next_sync: Optional[str]
    sync_status: str            # synced | pending | failed


@dataclass
class EmployeeData:
    """
    Unified employee data — returned by the Profile API or mock.

    Real API fields (GET /api/user/profile):
        remaining_count  — withdrawal eligibility (>0 = can withdraw)
        profile          — status, status_reason, remark, user_id, company_id
        company          — name, status
        bank_account     — bank_code, account_no, account_verify, …
        paycycle         — paycycle_status, start, cutoff, end, next_start
        deductions       — total_deducted, deductions_updated_at
        sync             — sync_type, schedules (list)

    Mock-only fields:
        attendance_snapshot — filtered attendance records (last 7 days)
    """
    employee_id: str
    remaining_count: int = 0
    profile: dict = field(default_factory=dict)
    company: dict = field(default_factory=dict)
    bank_account: dict = field(default_factory=dict)
    paycycle: dict = field(default_factory=dict)
    deductions: dict = field(default_factory=dict)
    sync: dict = field(default_factory=dict)
    attendance_snapshot: dict = field(default_factory=dict)


# ── Abstract client interfaces ────────────────────────────────────────────────

class BaseEmployeeDataClient(ABC):
    @abstractmethod
    def get_employee_data(self, employee_id: str = "") -> EmployeeData: ...


class BaseAttendanceClient(ABC):
    @abstractmethod
    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> dict: ...
