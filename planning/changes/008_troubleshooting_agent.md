# 008 — Troubleshooting Agent (LangChain Tool-Calling)

**Date:** 2026-04-01
**Type:** feature
**Phase:** 2

---

## Summary
Replaced the deterministic sequential planner with a LangChain `create_tool_calling_agent` (Claude Sonnet) that decides which diagnostic tools to call and stops early when a blocking root cause is found. Answer generation remains fully template-driven — the LLM does not write the final response.

## Added
- `agent/planner.py` — LangChain `AgentExecutor` with `return_intermediate_steps=True`; extracts `tool_outputs` from intermediate steps for evidence analysis
- `config/answer_templates.yaml` — YAML-driven answer templates for all root-cause scenarios (blacklisted, suspended, sync_pending, no_shift, attendance_remark, has_deductions, normal_active); bypasses LLM for final answer
- `agent/evidence.py` — `get_filled_template()` + `_build_response_guide()` for template variable filling; `_fmt_datetime()` for Thai/English ISO timestamp formatting; `_FOLLOWUP_QUESTIONS` per root cause
- `scripts/test_troubleshooting.py` — 10-scenario batch tester across 4 sections; prints ✅/❌ per scenario + accuracy summary
- `agent/clients/mock/users.json` — consolidated single mock data source (deleted redundant `mock_api_responses.json`); added `remarks` field to attendance records; added EMP003 attendance anomalies scenario

## Changed
- `agent/planner.py` — full rewrite from deterministic sequential logic to LangChain tool-calling agent
- `pipeline/answer_generator.py` — added `prefilled_answer` param (skips LLM when non-empty, returns `grounding_score=1.0`); added `top_retrieval_score` secondary escalation gate
- `agent/clients/base.py` — added `remarks: Optional[str]` to `AttendanceRecord`; removed `enrolled` field from `EmployeeStatus` (not present in real API)
- `pipeline/router.py` — added keywords: `ยอดเบิก`, `เป็น 0`, `เป็น0`, `ยอดเป็น 0`
- `interface/gradio_app.py` — added log/trace accordion panel; added `gr.State` follow-up question caching (reuses diagnostic context for same employee within session)
- `agent/evidence.py` — removed `RC_NOT_ENROLLED`; removed `[แนวทางการตอบ]` section from `format_for_llm` (redundant since template_answer is returned directly)

## Removed
- `agent/clients/mock/mock_api_responses.json` — replaced by `users.json` as single mock data source
- `enrolled` field from all mock data, base classes, and tool outputs

## Notes
- 100% accuracy on 10 mock scenarios across all root causes: sync_pending, blacklisted, suspended, attendance_remark (ok), normal_active (ok)
- `AGENT_LLM_MODEL` env var allows overriding the agent model (default: `claude-sonnet-4-6`)
- Root cause priority: blacklisted → suspended → sync_pending → no_shift → ok
