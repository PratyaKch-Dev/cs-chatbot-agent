"""
Abstract base classes for all HR API clients.

Two modes:
    Mock  — pass employee_id per method call, data loaded from users.json
    Real  — pass token at init, backend extracts employee_id from token

Interface keeps employee_id in signatures so LangChain tools work identically
in both modes. Real clients receive the token at construction and ignore
employee_id (the backend resolves the user from the Authorization header).
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
    status: str                 # present | absent | late | half_day


@dataclass
class AttendanceSummary:
    employee_id: str
    records: list[AttendanceRecord]
    total_present: int
    total_absent: int
    total_late: int


@dataclass
class ShiftInfo:
    shift_name: str
    start_time: str
    end_time: str
    days: list[str]


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
    enrolled: bool
    eligible_for_withdrawal: bool
    blacklisted: bool
    enrollment_date: Optional[str]


@dataclass
class SyncSchedule:
    employee_id: str
    last_sync: Optional[str]
    next_sync: Optional[str]
    sync_status: str            # synced | pending | failed


# ── Abstract client interfaces ────────────────────────────────────────────────
# employee_id is used by mock clients (JSON lookup).
# Real clients receive token at __init__ and let the backend resolve the user.

class BaseAttendanceClient(ABC):
    @abstractmethod
    def get_attendance(
        self, employee_id: str, date_from: str, date_to: str
    ) -> AttendanceSummary: ...


class BaseShiftClient(ABC):
    @abstractmethod
    def get_shift(self, employee_id: str) -> ShiftInfo: ...


class BaseDeductionClient(ABC):
    @abstractmethod
    def get_deductions(
        self, employee_id: str, period: str
    ) -> DeductionSummary: ...


class BaseEmployeeStatusClient(ABC):
    @abstractmethod
    def get_status(self, employee_id: str) -> EmployeeStatus: ...


class BaseSyncScheduleClient(ABC):
    @abstractmethod
    def get_sync_schedule(self, employee_id: str) -> SyncSchedule: ...
