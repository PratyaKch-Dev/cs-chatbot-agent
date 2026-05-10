# 018 — Attendance API Integration

**Date:** 2026-05-04
**Type:** feature
**Phase:** 3

---

## Summary
Replaced `MockAttendanceClient` stub with a real `AttendanceClient` calling `GET /api/user/attendance?date_from=&date_to=` using Bearer token. Introduced a shared token context var so both Profile and Attendance APIs receive the same token from a single `set_token()` call in the planner.

## Added
- `agent/tools/_token.py` — shared `ContextVar` (`set_token` / `get_token`) used by all agent tools so only one injection point is needed in the planner
- `agent/clients/attendance_client.py` — real `httpx` client; BE derives user from token, no `employee_id` in request; normalizes `metadata.remark` → `remarks` for uniform evidence handling

## Changed
- `agent/tools/employee_data.py` — imports `set_token`/`get_token` from shared `_token.py`
- `agent/tools/attendance.py` — rewired to shared token context; no module-level `_client` singleton (client instantiated per call with token)
- `agent/clients/mock/attendance_mock.py` — updated to read `_mock_attendance` key; normalizes `metadata.remark` → `remarks`; handles both old `remarks` and new `metadata.remark` shapes for backward compat
- `agent/clients/mock/users.json` — all `_mock_attendance.records` migrated to `metadata: {remark: "..."}` structure matching real API contract
- `agent/planner.py` — imports `set_token` from shared `_token.py`; `_extract_paycycle_start` updated to parse `paycycle.start` ISO datetime (new API) and `paycycle.start_date` (old mock fallback)

## Removed
- Module-level `_client = _Client()` singleton in attendance tool (was wrong for token injection)
- Per-tool `ContextVar` in `employee_data.py` (replaced by shared `_token.py`)

## Notes
- Real API endpoint: `GET /api/user/attendance?date_from={YYYY-MM-DD}&date_to={YYYY-MM-DD}`
- `date_from` = `paycycle.start` date part; `date_to` = today
- Attendance API is only called when `remaining_count = 0` and Profile API found no blocking issue (no inactive/deduction/bank problem)
- `metadata.remark` is normalized to `remarks` in client layer; evidence module unchanged
