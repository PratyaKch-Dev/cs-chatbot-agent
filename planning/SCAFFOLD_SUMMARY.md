# Scaffold Summary — What Was Created & Current State

This document is your checklist before starting Phase 1 implementation.
Every file is listed with its current state, what's already written, and what's left to implement.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully implemented / ready to use |
| 🟡 | Stub — structure + signatures written, logic not yet implemented |
| 📄 | Data / config file — content populated |
| 🧪 | Test file — test cases written (some runnable now) |

---

## Root Files

| File | State | What's Inside |
|------|-------|---------------|
| `main.py` | ✅ | CLI entry point — `python main.py api\|gradio` wired to FastAPI and Gradio |
| `requirements.txt` | ✅ | All dependencies pinned (fastapi, langchain, anthropic, sentence-transformers, qdrant, redis, gradio, pytest, etc.) |
| `.env.example` | ✅ | All required env vars documented with descriptions |
| `PLAN.md` | ✅ | 8-phase implementation plan with tasks, milestones, dependency order |

---

## `interface/` — Entry Points

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `fastapi_app.py` | 🟡 | FastAPI app, `/health` endpoint, LINE webhook skeleton, HMAC-SHA256 signature validation structure, tenant resolver stub | Phase 3: wire to orchestrator |
| `gradio_app.py` | 🟡 | Full Gradio UI layout — chat window, user ID input, send/clear buttons | Phase 3: replace `_chat()` stub with orchestrator call |

---

## `pipeline/` — Main Request Flow

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `orchestrator.py` | 🟡 | `RequestContext` and `ResponseContext` dataclasses defined, `handle_message()` stub | Phase 3: full pipeline logic |
| `router.py` | 🟡 | `Route` enum, `RouteDecision` dataclass, `TEMPLATE_INTENTS` set, `TROUBLESHOOTING_KEYWORDS` dict | Phase 3: routing logic |
| `safety.py` | 🟡 | `SafetyResult` dataclass, `IN_SCOPE_KEYWORDS` for Thai + English, `BLOCKED_PATTERNS` list | Phase 3: safety filter logic |
| `answer_generator.py` | 🟡 | `GeneratedAnswer` dataclass, `HANDOFF_THRESHOLD = 0.65` constant, `generate_answer()` and `_score_grounding()` stubs | Phase 3: LLM call + grounding scorer |
| `handoff.py` | 🟡 | `HandoffContext` dataclass with all fields, `build_handoff_context()` and `format_handoff_message()` stubs | Phase 3: conversation summarization + formatting |

---

## `rag/` — RAG / FAQ Retrieval Pipeline

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `embeddings.py` | 🟡 | `MODEL_NAME`, `EMBEDDING_DIM = 384`, `BATCH_SIZE = 16`, `@lru_cache(maxsize=500)` on `get_embedding_cached()`, `embed_documents()` and `embed_query()` stubs | Phase 2: load SentenceTransformer model |
| `reranker.py` | 🟡 | `MODEL_NAME = BAAI/bge-reranker-base`, `DEFAULT_THRESHOLD = 0.3`, `RerankResult` dataclass, `_sigmoid()` ✅ implemented | Phase 2: load CrossEncoder, implement `rerank()` |
| `query_cleaner.py` | 🟡 | `SYNONYM_MAP` with Thai + English entries, `_normalize_whitespace()` ✅, `_apply_synonyms()` ✅ | Phase 2: wire into `clean_query()` |
| `retriever.py` | 🟡 | `RetrievedDocument` and `RetrievalResult` dataclasses, `VECTOR_SEARCH_TOP_K = 10`, `RERANK_TOP_K = 5`, `_get_collection_name()` ✅ | Phase 2: Qdrant search + full pipeline |

---

## `agent/` — Troubleshooting Agent

### Core

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `planner.py` | 🟡 | `MAX_ITERATIONS = 10`, `MAX_EXECUTION_TIME = 30`, `AGENT_SYSTEM_PROMPT` template with all placeholders | Phase 5: `create_react_agent` + `AgentExecutor` setup |
| `evidence.py` | 🟡 | `DiagnosticContext` dataclass, `build_diagnostic_context()` and `format_for_llm()` stubs | Phase 5: parse tool JSONs, extract root cause |

### `agent/tools/` — LangChain Tools ✅ Wired to Mocks

All 5 tools are **fully wired** to mock clients via `USE_MOCK_APIS=true`. They produce structured JSON output immediately.

| File | State | LangChain docstring covers |
|------|-------|---------------------------|
| `attendance.py` | ✅ | Attendance history, absent/late days, salary deduction due to attendance |
| `shift.py` | ✅ | Work hours, shift assignment, which days to work |
| `deduction.py` | ✅ | Salary deduction breakdown, amounts and reasons |
| `employee_status.py` | ✅ | Withdrawal eligibility, enrollment status, blacklist check |
| `sync_schedule.py` | ✅ | Last/next sync time, sync failures, withdrawal limit not updated |

### `agent/clients/base.py` ✅

All 5 abstract base classes + shared data models defined:
`AttendanceSummary`, `ShiftInfo`, `DeductionSummary`, `EmployeeStatus`, `SyncSchedule`

### `agent/clients/mock/` ✅ — Ready to Use

All 5 mock clients return realistic fixture data for `employee_id = "EMP001"`:

| File | Returns |
|------|---------|
| `attendance_mock.py` | 4 records: 2 present, 1 late (Mar 25), 1 absent (Mar 26) |
| `shift_mock.py` | Morning Shift, 09:00–18:00, Mon–Fri |
| `deduction_mock.py` | Total 600 THB: 500 absent + 100 late |
| `employee_status_mock.py` | Active, enrolled, eligible, not blacklisted |
| `sync_schedule_mock.py` | Last sync Mar 27 02:00, next sync Mar 28 02:00, status: synced |

### `agent/clients/` — Real Clients 🟡

All 5 real clients exist as stubs — `raise NotImplementedError("Phase 8")`.

---

## `memory/` — Session + Conversation Memory

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `redis_client.py` | 🟡 | Singleton pattern, `check_redis_health()` stub | Phase 1: Redis connection with pooling |
| `session.py` | 🟡 | `SESSION_TTL_SECONDS = 1800`, `_session_key()` helper, all CRUD stubs | Phase 3: Redis CRUD |
| `history.py` | 🟡 | `HISTORY_TTL_SECONDS = 7 days`, `MAX_HISTORY_TURNS = 20`, `SUMMARIZATION_THRESHOLD = 15`, `is_history_too_long()` ✅, `_history_key()` ✅ | Phase 3: Redis list push/load |
| `summarizer.py` | 🟡 | `SUMMARY_TTL_SECONDS`, `_summary_key()` helper, all stubs | Phase 4: LLM summarization |

**Redis key schema already defined:**
- `chat:session:{tenant_id}:{user_id}`
- `chat:memory:{tenant_id}:{user_id}:{language}`
- `chat:summary:{tenant_id}:{user_id}:{language}`

---

## `llm/` — LLM + Language Utilities

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `client.py` | 🟡 | `MODEL_NAME = claude-3-haiku`, `DEFAULT_MAX_TOKENS`, `MAX_RETRIES`, `_get_fallback_response()` ✅ in Thai + English | Phase 1: anthropic SDK call with tenacity retry |
| `intent.py` | 🟡 | `Intent` enum (7 types), `INTENT_KEYWORDS` dict with Thai + English per intent | Phase 2: keyword matching logic |
| `language.py` | 🟡 | `is_thai()` ✅ (Unicode range check), `detect_language()` returns hardcoded `'th'` with TODO | Phase 2: PyThaiNLP + langdetect |
| `templates.py` | ✅ | All 6 Thai + English templates fully written: greeting, thanks, goodbye, frustrated, confused, unclear. `get_template()` implemented |

---

## `domain/` — Salary Hero Business Logic

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `withdraw_diagnosis.py` | 🟡 | `WithdrawalFailureCase` enum (6 cases), `WithdrawalDiagnosis` dataclass, `_check_blocked()` ✅, `_check_blacklisted()` ✅, `_check_enrolled()` ✅, `_check_sync_pending()` ✅ | Phase 6: `diagnose_withdrawal_failure()` rule logic |
| `withdraw_formatter.py` | 🟡 | `_THAI_MESSAGES` and `_ENGLISH_MESSAGES` dicts fully populated for all 6 cases | Phase 6: `format_diagnosis()` string builder |

---

## `observability/` — Tracing & Metrics

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `tracing.py` | 🟡 | `setup_tracing()` no-ops gracefully if no API key, `trace_request()` stub | Phase 7: LangSmith integration |
| `metrics.py` | 🟡 | `RequestMetric` dataclass, `record_metric()` no-op (won't crash), `get_escalation_rate()` stub | Phase 7: metrics backend |

---

## `evaluation/` — Offline Metrics

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `rag_eval.py` | 🟡 | `RAGEvalResult` dataclass, `run_rag_eval()` stub | Phase 7: ragas integration |
| `agent_eval.py` | 🟡 | `AgentEvalResult` dataclass, `run_agent_eval()` stub | Phase 7: tool accuracy scorer |
| `datasets/rag_test_cases.json` | 📄 | 5 Thai + English test cases with expected answers |
| `datasets/agent_test_cases.json` | 📄 | 3 troubleshooting scenarios with expected tool calls |

---

## `indexers/` — Offline Knowledge Pipeline

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `index_faq_csv.py` | 🟡 | CLI arg parsing (`--file`, `--company`, `--language`), `_read_csv()` ✅, CSV column validation | Phase 2: embed + Qdrant upsert |
| `merge_data.py` | 🟡 | CLI arg parsing, file path constants | Phase 8: deduplication + merge |
| `inspect_qdrant.py` | 🟡 | CLI arg parsing (`--collection`, `--limit`) | Phase 2: Qdrant list/inspect |

---

## `config/` — YAML Configuration

| File | State | What's Inside |
|------|-------|---------------|
| `tenants.yaml` | 📄 | HNS tenant fully configured: company_id, languages, LINE tokens, vector collections, feature flags, handoff method |
| `incident_data.yaml` | 📄 | 3 active incidents: salary delay, maintenance window (Apr 5), iOS 17 login bug |

---

## `data/` — Knowledge Sources

| File | State | Rows | Content |
|------|-------|------|---------|
| `data/faqs/public_faq.csv` | 📄 | 9 | General Salary Hero Q&A in Thai |
| `data/faqs/public_incident.csv` | 📄 | 0 | Empty template |
| `data/company/hns/hns_company.csv` | 📄 | 4 | HNS-specific: withdrawal hours, holiday rules, transfer timing, eligibility |

---

## `tests/` — Test Suite

### Unit Tests

| File | State | Runnable Now? |
|------|-------|---------------|
| `test_intent.py` | 🧪 | After Phase 2 |
| `test_language.py` | 🧪 | `test_is_thai_*` run now; `test_detect_language` after Phase 2 |
| `test_router.py` | 🧪 | After Phase 3 |
| `test_safety.py` | 🧪 | After Phase 3 |
| `test_reranker.py` | 🧪 | `TestSigmoid.*` runs now ✅; reranker tests after Phase 2 |
| `test_withdraw_diagnosis.py` | 🧪 | `TestHelperFunctions.*` runs now ✅; full diagnosis after Phase 6 |

### Integration Tests

| File | State | Runnable Now? |
|------|-------|---------------|
| `test_agent_tools.py` | 🧪 | **All 5 tool tests run now ✅** (mock clients) |
| `test_rag_pipeline.py` | 🧪 | After Phase 2 (needs Qdrant populated) |

### Fixtures

| File | Content |
|------|---------|
| `tests/fixtures/sample_messages.json` | 10 Thai + English messages covering all intent types |
| `tests/fixtures/mock_api_responses.json` | Complete mock data for all 5 APIs for EMP001 |

---

## What You Can Run Right Now

```bash
# Install dependencies
pip install -r requirements.txt

# These pass immediately (no external services needed)
pytest tests/integration/test_agent_tools.py -v
pytest tests/unit/test_reranker.py::TestSigmoid -v
pytest tests/unit/test_withdraw_diagnosis.py::TestHelperFunctions -v
pytest tests/unit/test_language.py::TestIsThai -v
```

---

## Phase 1 Starting Point

The next thing to implement is **Phase 1: Foundation**.
Start with these files in order:

1. `memory/redis_client.py` — Redis singleton
2. `llm/client.py` — Claude wrapper
3. `interface/fastapi_app.py` — complete LINE webhook

All three can be independently developed and tested before wiring them together in `pipeline/orchestrator.py`.
