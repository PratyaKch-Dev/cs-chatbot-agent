# 009 — Troubleshooting Agent Improvements

**Date:** 2026-04-02
**Type:** fix + feature + data
**Phase:** 2

---

## Summary
Improvement pass on the troubleshooting agent: added `no_shift` scenario end-to-end, added EMP006 mock data and test cases, fixed all dead code and display bugs, and added API retry logic for overloaded responses.

## Added
- `no_shift` scenario in `_build_response_guide` — now correctly picked when `root_cause == RC_NO_SHIFT` instead of falling through to `normal_active`
- `no_shift` template in `config/answer_templates.yaml` (th + en) — tells user to ask manager/HR to assign a shift
- `EMP006` in `agent/clients/mock/users.json` — "No shift assigned" scenario with empty `days: []` and null start/end times
- EMP006 test cases in `scripts/test_troubleshooting.py` — 2 scenarios, section "ไม่มีกะงาน (no shift assigned)"; total now 12/12 ✅
- Retry logic in `agent/planner.py` — exponential backoff (1s, 2s) on `overloaded`/`529`/`rate` API errors; up to 2 retries before logging and continuing

## Changed
- `agent/planner.py` — system prompt: removed stale "not enrolled" reference; added `→ If shift has no days assigned: STOP` to step 3
- `agent/evidence.py` — shift detail section: suppresses `เวลา` line when `start_time`/`end_time` are null; shows "ยังไม่ได้ตั้งค่า" for empty shift name
- `agent/evidence.py` — removed `enrolled` references from `_format_detail_sections` (field no longer exists)
- `agent/evidence.py` — docstring: removed `not_enrolled` from root cause priority list

## Removed
- `_extract_status_summary()` dead function from `agent/evidence.py`
- `no_deductions` template from `config/answer_templates.yaml` (no code path ever selected it)
- `sync_ok` template from `config/answer_templates.yaml` (unused)

## Notes
- All 12 test scenarios pass at 100% accuracy after improvements
- Shift display degrades gracefully: normal shifts show name + hours + days; unassigned shifts show "ยังไม่ได้ตั้งค่า" + "ยังไม่มีกะ" with no hours line
