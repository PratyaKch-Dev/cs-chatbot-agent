"""
Integration tests for the troubleshooting agent tools.

Uses mock clients — no real API calls.
"""

import pytest
import json


@pytest.mark.integration
class TestAgentToolsWithMocks:
    def test_attendance_tool_returns_json(self):
        from agent.tools.attendance import get_attendance_records
        result = get_attendance_records.invoke({
            "employee_id": "EMP001",
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
        })
        data = json.loads(result)
        assert "records" in data
        assert "total_present" in data

    def test_shift_tool_returns_json(self):
        from agent.tools.shift import get_shift_schedule
        result = get_shift_schedule.invoke({"employee_id": "EMP001"})
        data = json.loads(result)
        assert "shift_name" in data
        assert "days" in data

    def test_deduction_tool_returns_json(self):
        from agent.tools.deduction import get_salary_deductions
        result = get_salary_deductions.invoke({
            "employee_id": "EMP001",
            "period": "2026-03",
        })
        data = json.loads(result)
        assert "items" in data
        assert "total_deducted" in data

    def test_employee_status_tool_returns_json(self):
        from agent.tools.employee_status import get_employee_status
        result = get_employee_status.invoke({"employee_id": "EMP001"})
        data = json.loads(result)
        assert "status" in data
        assert "enrolled" in data

    def test_sync_schedule_tool_returns_json(self):
        from agent.tools.sync_schedule import get_sync_schedule
        result = get_sync_schedule.invoke({"employee_id": "EMP001"})
        data = json.loads(result)
        assert "sync_status" in data
        assert "last_sync" in data
