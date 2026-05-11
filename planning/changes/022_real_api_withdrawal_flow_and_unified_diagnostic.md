# 022 — Real-API Withdrawal Flow, Unified Diagnostic & Routing Fixes

**Date:** 2026-05-12
**Type:** feature + refactor + fix
**Phase:** 3

---

## Summary
End-to-end real-API integration for the troubleshooting_withdrawal flow (profile + balance + attendance) with a new 3-section composite diagnostic, a unified `คำแนะนำ:` suggestion block, hot-reloadable YAML strings, API-failure surfacing, and several routing/UX fixes.

## Added
- **Balance API client** (`agent/clients/balance_client.py`) — `GET /api/v1/user/ewa/balance/withdraw`; returns both `earned_avaliable_amount` (BE typo) and `earned_available_amount` (clean alias); same Bearer + app-identity headers + SSL bypass switch as the other clients.
- **Balance tool + mock** (`agent/tools/balance.py`, `agent/clients/mock/balance_mock.py`) — LangChain `@tool` `get_balance(employee_id)` selecting real vs mock by token presence.
- **Editable mock fixture** (`agent/clients/mock/_mock_data.py`) — single source of truth mirroring the real BE shape for PROFILE, BALANCE, ATTENDANCE; uses `importlib.reload` so edits take effect on the next message without restart; scenario cookbook in the module docstring.
- **`get_balance` planner strategy** — `troubleshooting_withdrawal` now plans `[get_employee_data, get_balance, get_attendance]`; profile + balance run in parallel via `ThreadPoolExecutor`; attendance runs after (needs `paycycle.start`).
- **3-section withdrawal diagnostic** in `agent/evidence.py`:
  - §1 balance header (`ยอดเบิกได้ตอนนี้` + status)
  - §2 eligibility checklist (6 binary checks: status, no_remark, bank, paycycle_active, in_window, fresh_data)
  - §3 balance factors (deductions + full attendance table with inline HR remarks)
  - §4 unified `คำแนะนำ:` section consolidating all action lines + friendly all-clear closing for the happy path
- **YAML-driven copy** — new `withdrawal_diagnostic` block in `config/answer_templates.yaml` (Thai + English) covering all section labels, per-check pass/fail/action text, status translation map, all-clear message, and `api_errors`. Hot-reload on file mtime change.
- **API-failure surfacing** — `_ts_section_api_errors` detects per-tool `{"error": …}` blobs, special-cases HTTP 401 as "session expired, please sign in again", and renders a ⚠️ footer (or replaces the whole answer when profile failed). Planner now persists exceptions into `tool_outputs[name]` as JSON errors so this detection has something to read.
- **Gradio Bearer token + Test API probe** (`interface/gradio_app.py`) — token textbox (type=password); Test API call moved into an accordion below `Pipeline trace (last request)`; probe hits all 3 endpoints (profile + balance parallel, then attendance) and shows status/payload preview.
- **Spec doc** `planning/USER_PROFILE_API_SPEC.md` — full decision-tree priority order, BE response shape, binary status values, real-API field reference.

## Changed
- **`employee_data_client.py`** — endpoint to `/api/v1/user/account/chatbot/profile`; reads `paycycle.employee_data_status` (with top-level fallback); adds Authorization Bearer + language + x-os-platform + x-device-id + x-app-version + User-Agent + Cache-Control + Pragma headers; SSL verify toggle via `API_VERIFY_SSL`.
- **`attendance_client.py`** — endpoint to `/api/v1/user/account/chatbot/attendance`; same header pattern + SSL toggle.
- **`agent/clients/base.py`** — `EmployeeData` dataclass gains `employee_data_status` field.
- **`agent/tools/employee_data.py` + `attendance.py`** — default `USE_MOCK_APIS=false`; selection rule = token presence; mock fallback only when no token or `USE_MOCK_APIS=true`.
- **`agent/evidence.py`** — heavy refactor: new RC constants (`RC_PAYCYCLE_INACTIVE`, `RC_OUTSIDE_PAYCYCLE`, `RC_PAST_CUTOFF`, `RC_DATA_OUTDATED`, `RC_HAS_REMARK`); `_check_paycycle_window` (BKK/UTC aware); `_identify_root_cause` priority order rewritten; `_load_templates` hot-reloads via mtime; profile name resolution no longer leaks `context.employee_id` (uses `profile.get("name") or "คุณ"/"you"`); `_ts_is_all_clear` rejects all-clear when any tool has an error.
- **`config/answer_templates.yaml`** — `withdrawal_diagnostic` block; `balance_status_actions.not_ready` rewritten to direct user to HR (balance status is binary `ready|not_ready`); `factors_header` updated to `"ทำไมยอดเงินถึงยังไม่ขึ้น หรือเบิกไม่ได้:"`; consolidated action lines under `suggestions_header`.
- **`pipeline/router.py`** — added `handoff_request` intent label that routes any "talk to human" wording into TROUBLESHOOTING for explicit handoff.
- **`pipeline/context_resolver.py`** — removed substring `_is_no` keyword match from `awaiting_confirmation` branch (was wrongly firing on "ทำไมเบิกเงินไม่ได้" via the substring "ไม่ได้"); LLM router with active context is now the single source of truth for non-yes replies. Length-bounded `_is_handoff_request` detection for "โอน"/"transfer" variants.
- **`pipeline/orchestrator.py`** —
  - `template_key == "handoff_request"` short-circuits to `run_handoff_summary` immediately.
  - Stale `retry_count` reset to 0 when the current turn is CHITCHAT/MISSING_INFO/FAQ.
  - Topic-preservation override: when LLM says `is_new=True` but `sub_type` matches the active context, force `is_new=False` to preserve retry_count.
  - MISSING_INFO safety net for troubleshooting `awaiting_confirmation` now guards on `not decision.is_new` — fresh preambles like "สอบถามหน่อย" are no longer coerced into a recheck.
- **`agent/planner.py`** — tool failures (exceptions from `pool.submit().result()` or `get_attendance.invoke()`) are now persisted into `tool_outputs[name]` as JSON `{"error": …}` so the evidence layer can surface them.
- **`interface/gradio_app.py`** — removed Employee ID textbox (real-API only now); `emp_input` becomes a hidden `gr.State("mock_user")` placeholder; token field labeled as required; markdown blurb updated.
- **`.env.example`** — documents `INTERNAL_API_BASE_URL`, `API_VERIFY_SSL`, `API_DEVICE_ID`, `API_APP_VERSION`, `API_OS_PLATFORM`, `API_USER_AGENT`.

## Removed
- Inline action lines under each §2 ✗ row and the standalone deduction/missing-check action lines in §3 — all suggestions now flow into the unified `คำแนะนำ:` block.
- `apply_overrides` / `apply_balance_overrides` hooks from the real clients (real-API responses are never patched in-flight).
- `_test_override.py` mock-override module (superseded by editable `_mock_data.py` fixture).
- `_is_no` keyword check from the `awaiting_confirmation` resolver branch.
- "Mock vs Real" markdown blurb in Gradio (mock toggle is now token-driven, not UI-driven).

## Notes
- BE derives `user_id` from the Bearer token — `employee_id` is no longer trusted by the real API path. Mock path still keys on the param.
- All 24 withdrawal-diagnostic cases (§1 balance variants, §2 single-failure modes, §3 deduction/attendance variants, COMBO end-to-end) are regenerated and saved to `logs/withdrawal_diagnostic_cases.log`.
- Hot-reload: editing `_mock_data.py` or `answer_templates.yaml` while Gradio is running takes effect on the next message — no restart needed.
- Token expiry surfaces as "เซสชันของคุณหมดอายุแล้ว กรุณาเข้าสู่ระบบใหม่อีกครั้งค่ะ" / English equivalent.
- Known limitation: `ContextVar`-based token injection does not propagate into `ThreadPoolExecutor` workers, so profile + balance run with empty token in the parallel phase and fall back to mock. Attendance (phase 2, main thread) sees the real token. Follow-up work needed: pass the token explicitly into the worker closures instead of via ContextVar.
