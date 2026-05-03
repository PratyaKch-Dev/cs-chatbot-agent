# 013 — Solutions FAQ Pipeline + Answer Template Refinements

**Date:** 2026-05-03
**Type:** feature + data + refactor
**Phase:** 2

---

## Summary
Full Freshdesk Solutions.json → Qdrant pipeline: converter, per-company indexer, and `/solutions` skill. Answer templates rewritten for clarity, mock data extended with a new EMP007 deduction scenario, and pipeline internals refined (router, orchestrator, retriever, logger).

## Added
- `indexers/convert_solutions_json.py` — converts Freshdesk Solutions.json to `data/faqs/solutions_faq.csv` with per-company tagging
- `indexers/index_solutions.py` — indexes solutions CSV per-company into Qdrant (company-specific + all defaults merged into each collection)
- `indexers/qdrant_dashboard.py` — inspect Qdrant collections interactively
- `.claude/skills/solutions/SKILL.md` — `/solutions` skill: convert + index + verify in one command
- `data/faqs/solutions_faq.csv` — 2,589-row FAQ extracted from Freshdesk Solutions (default + company-specific articles)
- `_test_e2e_chat.py` — 53-case end-to-end chat test covering all articles in the `happy_nest_space` collection
- `test_router_retrieval.py` — router + retrieval integration tests
- `agent/clients/mock/users.json` — new EMP007 scenario: deductions reduce balance to 0, `eligible_for_withdrawal: false`, no blacklist

## Changed
- `config/answer_templates.yaml` — rewrote all 7 templates (normal_active, status_inactive, suspended, blacklisted, attendance_remark, has_deductions, sync_pending) for shorter, more direct Thai/English wording; reordered suspended ↔ blacklisted sections; added `{attendance_table}` variable docs
- `agent/clients/mock/attendance_mock.py` — `MAX_ATTENDANCE_DAYS` default 30 → 60
- `agent/clients/mock/users.json` — EMP001 deductions simplified (removed period + items, kept total + timestamp)
- `pipeline/router.py`, `pipeline/orchestrator.py`, `pipeline/answer_generator.py` — pipeline internals refined
- `rag/retriever.py` — retrieval adjustments
- `utils/pipeline_logger.py` — logger improvements
- `interface/gradio_app.py` — minor UI updates
- `planning/PRESENTATION.md` — updated

## Removed
- `data/faqs/public_incident.csv` — was an empty header-only file
- `data/merged/hns_th.csv` — stale merged output; regenerated on demand

## Notes
- Each Qdrant collection is self-contained: company-specific articles + all 52 default articles merged in
- Source types: `non_login`, `login`, `feature_sod`, `feature_flexben`, `feature_direct_debit`
- Tags: `default` (all companies) vs `company_specific` (one company only)
