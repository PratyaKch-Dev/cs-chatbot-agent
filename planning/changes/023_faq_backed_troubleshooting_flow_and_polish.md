# 023 — FAQ-Backed Troubleshooting Flow, Token Propagation Fix & UX Polish

**Date:** 2026-05-12
**Type:** refactor + fix + feature
**Phase:** 3

---

## Summary
Unified the troubleshooting UX so all four `troubleshooting_*` sub_types (signup, cant_find_company, money_not_arrived, cant_receive_otp) get the same confirmation → recheck → handoff scaffolding as `troubleshooting_withdrawal`, with FAQ retrieval as the answer source. Also fixed the ContextVar token-propagation bug in the parallel API workers and polished several diagnostic copy details.

## Added
- **`_run_faq_backed_ts` orchestrator handler** — sub_types in the new `_FAQ_BACKED_TS_SUBTYPES` set get their answer from the pinned FAQ article (via `_run_faq` with `is_new=True` forced on a proxy `RouteDecision`) and have `save_troubleshooting_context` called so the active-context machinery treats them like withdrawal.
- **`_FAQ_BACKED_TS_SUBTYPES` set + `_is_faq_backed_ts` helper** in `pipeline/orchestrator.py` — single switch governing which sub_types currently live in FAQ-backed mode. Migration path documented: move a sub_type out of the set + add its tools to `_TOOL_STRATEGY` when its real-API integration lands.
- **Per-worker token re-injection** in `agent/planner.py` — new `_with_token(fn)` closure inside `run_troubleshooting_agent` re-sets the access token inside each ThreadPoolExecutor worker so real-API calls fire for profile + balance (previously the workers silently fell back to mock because `ContextVar` does not propagate to executor threads).
- **`attendance_remark_hint`** YAML string + render logic — when any attendance row carries a remark (HR note, system flag, free-form text), the §3 header gains a one-line cue: `อาจเป็นเพราะมีหมายเหตุในวันที่เข้า-ออกงาน ทำให้ยอดเงินไม่อัปเดต` (EN parallel added).
- **`action_attendance_remark`** YAML template — surfaced under `คำแนะนำ:` when remarks exist; names the specific date(s) that carry a remark (e.g. `วันที่ 12 พ.ค. 2026, 11 พ.ค. 2026 อาจไม่ได้อัปเดตจำนวนเงินเพราะมีหมายเหตุจาก HR — ติดต่อ HR เพื่อสอบถามรายละเอียด`).
- **Topic mappings** in `_TS_TOPIC` for the 4 FAQ-backed sub_types (`signup_issue`, `company_search_issue`, `money_not_arrived_issue`, `otp_issue`).

## Changed
- **`pipeline/router.py`** — all four formerly-FAQ-routed troubleshooting labels (`troubleshooting_signup`, `troubleshooting_cant_find_company`, `troubleshooting_money_not_arrived`, `troubleshooting_cant_receive_otp`) now map to `Route.TROUBLESHOOTING` so the troubleshooting branch handles them.
- **`pipeline/orchestrator.py`**
  - `_run_troubleshooting_new` + `_run_troubleshooting_recheck` short-circuit to `_run_faq_backed_ts` when sub_type is FAQ-backed (uses active_ctx.sub_type on rechecks).
  - Top-level pinned-FAQ shortcut (lines 446–482 previously) removed — the pin still fires inside `_run_faq`, but the answer now flows through the troubleshooting branch so confirmation/recheck/handoff wraps it.
  - `MAX_TROUBLESHOOTING_RETRIES` reduced from 3 → 2 (recheck #1 → ask; recheck #2 → surface `• ต้องการโอนไปให้เจ้าหน้าที่ช่วย` option).
  - MISSING_INFO safety net for troubleshooting awaiting_confirmation now guards on `not decision.is_new` — fresh preambles like `สอบถามหน่อย` are no longer coerced into a recheck loop; short ambiguous replies (`เจออยู่`, `ก็ยังนะ`) still get coerced because the router marks those `is_new=False`.
- **`agent/evidence.py`**
  - `_ts_section_balance_factors` — prepends the new remark hint under `factors_header` when any record carries a remark; reads `metadata.remark` first with legacy `remarks` fallback.
  - `_ts_section_suggestions` — split attendance-issue handling into two distinct paths: `action_attendance_remark` (names the dates that carry remarks) and `action_missing_check` (only fires for rows missing a punch without a remark, so the two don't double up when a remark already explains the missing punch).
  - `_format_attendance_table` + `format_for_llm` remarks-list now read `metadata.remark` first with `remarks` fallback (consistent shape with BE).
- **`config/answer_templates.yaml`**
  - `action_missing_check` rewritten in pure Thai: `→ ติดต่อ HR ให้บันทึกเวลาเข้า-ออกงานย้อนหลัง (ยอดจะอัปเดตในรอบถัดไป)` — drops the English `check_in/out` and `sync` jargon.
  - Added `attendance_remark_hint` + `action_attendance_remark` under both `th` and `en` blocks.
- **`pipeline/context_resolver.py`**
  - `_YES_WORDS` expanded with Thai resolution phrases (`เจอแล้ว`, `สำเร็จ`, `สำเร็จแล้ว`, `เรียบร้อยแล้ว`, `หายแล้ว`, `เคลียร์`, `ทำได้`, `ทำได้แล้ว`, `แก้ได้แล้ว`, `ใช้ได้แล้ว`, `โอเคแล้ว`, `okay`) and English (`fixed`, `works`, `it works`, `got it`, `all good`). Substring-trap traps documented inline (`เสร็จ`, `ได้เลย` deliberately excluded).
- **`agent/planner.py`** — token injection comments updated; planner's main-thread `set_token` kept for Phase 2 attendance which runs synchronously.

## Removed
- **Top-level pinned-FAQ shortcut** in `pipeline/orchestrator.py` — superseded by the unified troubleshooting branch. Pinning still happens inside `_run_faq`; only the duplicate top-level path that bypassed all scaffolding was deleted.
- **`_is_no` + `_NO_WORDS`** in `pipeline/context_resolver.py` — the keyword-based "no" check was already disabled in the awaiting_confirmation branch (in 022) and had no remaining callers. The LLM router with active-context is the sole non-yes-reply judge now.

## Notes
- **Migration path for new real-API troubleshooting flows:** drop the sub_type from `_FAQ_BACKED_TS_SUBTYPES` and populate its entry in `agent/planner.py :: _TOOL_STRATEGY` with the tools to call. No other code needs to change — `_run_troubleshooting_new` and `_run_troubleshooting_recheck` automatically take the agent path when the sub_type isn't FAQ-backed.
- **ContextVar caveat:** Python's `concurrent.futures.ThreadPoolExecutor` does **not** propagate ContextVar values into worker threads. The `_with_token` wrapper is the explicit fix; future tools added to Phase 1 parallel execution must also go through it (or set the token inside their own closure) — verified with a `python -c` test showing both workers now see the Bearer token.
- **Free-form remark text** is rendered next to the attendance row (e.g. `"มาสาย"`, `"ลาป่วย"`, `"ลืม check in"`) but the suggestion line stays generic with date list only — keeps the copy stable regardless of what HR/system writes in the remark field.
- All 25 withdrawal-diagnostic cases (with new §3.10 multi-remark case) regenerated to `logs/withdrawal_diagnostic_cases.log` after each set of changes; final file is 34 KB.
