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
    remarks: Optional[str] = None   # e.g. "ลืม check in", "บัตรเสีย — HR บันทึกให้"


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
    Returned by the first API call — profile, sync, deductions, pay cycle,
    and a short attendance snapshot (≤7 days, from paycycle start).
    """
    employee_id: str
    profile: dict
    sync: dict
    deductions: dict
    paycycle: dict              # {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    attendance_snapshot: dict   # filtered to max(paycycle_start, today-7d) → today


# ── Abstract client interfaces ────────────────────────────────────────────────

class BaseEmployeeDataClient(ABC):
    @abstractmethod
    def get_employee_data(self, employee_id: str) -> EmployeeData: ...


class BaseAttendanceClient(ABC):
    @abstractmethod
    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> dict: ...
