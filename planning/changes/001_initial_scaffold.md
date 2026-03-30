# 001 — Initial Scaffold + PLAN.md

**Date:** 2026-03-29
**Type:** scaffold
**Phase:** pre-phase

---

## Summary

Full project scaffold — 80 files created across all packages.
Established folder structure, stubs, configs, data, and tests.

---

## Added

**Root**
- `main.py` — CLI entry point (`python main.py api|gradio`)
- `requirements.txt` — all dependencies pinned
- `.env.example` — all required env vars documented
- `PLAN.md` — 8-phase implementation plan

**`interface/`**
- `fastapi_app.py` — LINE webhook skeleton with HMAC-SHA256 signature validation
- `gradio_app.py` — Gradio test UI layout

**`pipeline/`**
- `orchestrator.py` — `RequestContext` + `ResponseContext` dataclasses, `handle_message()` stub
- `router.py` — `Route` enum, `RouteDecision` dataclass, keyword maps
- `safety.py` — `SafetyResult` dataclass, in-scope keyword lists
- `answer_generator.py` — `GeneratedAnswer` dataclass, `HANDOFF_THRESHOLD = 0.65`
- `handoff.py` — `HandoffContext` dataclass, warm handoff stubs

**`rag/`**
- `retriever.py` — `RetrievedDocument` + `RetrievalResult` dataclasses, `VECTOR_SEARCH_TOP_K = 10`
- `embeddings.py` — `@lru_cache(maxsize=500)` on `get_embedding_cached()`, `EMBEDDING_DIM = 384`
- `reranker.py` — `DEFAULT_THRESHOLD = 0.3`, `_sigmoid()` implemented
- `query_cleaner.py` — `SYNONYM_MAP`, `_normalize_whitespace()` + `_apply_synonyms()` implemented

**`agent/`**
- `planner.py` — `MAX_ITERATIONS = 10`, `AGENT_SYSTEM_PROMPT` template
- `evidence.py` — `DiagnosticContext` dataclass
- `tools/` — 5 LangChain `@tool` wrappers (attendance, shift, deduction, employee_status, sync_schedule)
- `clients/base.py` — abstract interfaces + shared data models (5 dataclasses)
- `clients/` — 5 real client stubs
- `clients/mock/` — 5 mock clients with hardcoded fixture data

**`memory/`**
- `redis_client.py` — singleton pattern stub
- `session.py` — `SESSION_TTL_SECONDS = 1800`, `_session_key()` helper
- `history.py` — `HISTORY_TTL_SECONDS`, `is_history_too_long()` + `_history_key()` implemented
- `summarizer.py` — `_summary_key()` helper

**`llm/`**
- `client.py` — `MODEL_NAME`, fallback response implemented
- `intent.py` — `Intent` enum (7 types), `INTENT_KEYWORDS` Thai + English
- `language.py` — `is_thai()` (Unicode range) implemented, `detect_language()` hardcoded `'th'`
- `templates.py` — all 6 Thai + English templates fully written, `get_template()` implemented

**`domain/`**
- `withdraw_diagnosis.py` — `WithdrawalFailureCase` enum (6 cases), 4 helper checks implemented
- `withdraw_formatter.py` — all 6 Thai + English message dicts fully written

**`observability/`**
- `tracing.py` — no-op until Phase 7
- `metrics.py` — `RequestMetric` dataclass, `record_metric()` no-op

**`evaluation/`**
- `rag_eval.py` — `RAGEvalResult` dataclass
- `agent_eval.py` — `AgentEvalResult` dataclass
- `datasets/rag_test_cases.json` — 5 Thai + English test cases
- `datasets/agent_test_cases.json` — 3 troubleshooting scenarios

**`indexers/`**
- `index_faq_csv.py` — CLI args + `_read_csv()` implemented
- `merge_data.py` — stub (implemented in change 002)
- `inspect_qdrant.py` — CLI args

**`config/`**
- `tenants.yaml` — HNS tenant fully configured
- `incident_data.yaml` — 3 active incidents

**`data/`**
- `faqs/public_faq.csv` — 9 rows
- `faqs/public_incident.csv` — empty template
- `company/hns/hns_company.csv` — 4 rows

**`tests/`**
- Unit: `test_intent`, `test_language`, `test_router`, `test_safety`, `test_reranker`, `test_withdraw_diagnosis`
- Integration: `test_agent_tools` (runnable immediately), `test_rag_pipeline`
- Fixtures: `sample_messages.json` (10 messages), `mock_api_responses.json`

**`planning/`**
- `ARCHITECTURE.md`, `SCAFFOLD_SUMMARY.md`
