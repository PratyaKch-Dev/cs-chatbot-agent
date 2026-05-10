# 017 — User Profile API Integration

**Date:** 2026-05-04
**Type:** feature
**Phase:** 3

---

## Summary
Replaced `MockEmployeeDataClient` with a real `EmployeeDataClient` that calls `GET /api/user/profile` using a Bearer token. Diagnosis logic now covers all new API fields: account status + status_reason, deductions, bank account existence/verification, and sync schedules.

## Added
- `agent/clients/employee_data_client.py` — real HTTP client calling `GET /api/user/profile` via `httpx`; BE derives user from token (no employee_id trusted from FE)
- `memory/token_store.py` — Redis store for access_token keyed by LINE user_id (`auth:token:{user_id}`, TTL 24h)
- `POST /auth/token` endpoint in `fastapi_app.py` — mobile app registers Salary Hero access_token for a LINE user before troubleshooting
- New root causes in `evidence.py`: `RC_DEDUCTION`, `RC_NO_BANK`, `RC_BANK_UNVERIFIED`
- New answer templates: `no_bank`, `bank_unverified`; updated `has_deductions`, `status_inactive`, `suspended` to include `{status_reason_line}`
- `_format_sync_schedules()` helper — renders `sync.schedules` list into TH/EN display string
- `agent/tools/employee_data.py` — `set_token()` / `_token_ctx` (contextvars) for per-request token injection without changing tool signature

## Changed
- `agent/clients/base.py` — `EmployeeData` updated to match real API shape: added `remaining_count`, `bank_account`, `company`; removed old mock-only fields from dataclass signature
- `agent/clients/mock/employee_data_mock.py` — rewritten to read new JSON format directly (no old→new mapping); `_mock_sync_status` promoted to `sync.sync_status` for sync_pending test scenario
- `agent/clients/mock/users.json` — all 7 employees rewritten to match real API response structure (`remaining_count`, `profile.status_reason`, `bank_account`, `paycycle.paycycle_status`, `sync.schedules`); attendance moved to `_mock_attendance` key
- `agent/clients/mock/attendance_mock.py` — reads `_mock_attendance` key (falls back to `attendance` for backward compat)
- `agent/evidence.py` — `_identify_root_cause` priority updated: remaining_count → blacklist → status → deduction → no_bank → bank_unverified → sync_pending → ok; formatters updated for new API fields
- `agent/planner.py` — accepts `access_token` param; calls `set_token()` before tool invocations
- `pipeline/orchestrator.py` — `handle_message` loads `access_token` from Redis by user_id; passes it to both troubleshooting sub-handlers
- `config/answer_templates.yaml` — added `no_bank`, `bank_unverified` scenarios; updated `status_inactive`/`suspended` to include `{status_reason_line}`; updated `has_deductions` to use `{total_deducted}`

## Removed
- Old mock-format mapping code in `MockEmployeeDataClient` (eligible_for_withdrawal, blacklisted, enrollment_date translation)

## Notes
- `USE_MOCK_APIS=true` still works end-to-end for local testing without a real API
- Real client skips `employee_id` param — BE derives user from Bearer token
- `sync.schedules` is display-only; no runtime logic depends on it
- `account_no` is already masked by BE (`XXXXXX9058`) — chatbot never sees full account number
