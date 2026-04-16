# Scaffold Summary — What Was Created & Current State

This document tracks the current implementation state across all modules.
Last updated: 2026-04-01

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully implemented / ready to use |
| 🟡 | Stub — structure + signatures written, logic not yet implemented |
| 📄 | Data / config file — content populated |
| 🧪 | Test file — test cases written (some runnable now) |

---

## Implementation Progress

| Phase | Description | Status |
|-------|-------------|--------|
| Pre-phase | Scaffold, config, skills, Docker | ✅ Done |
| Phase 2 | FAQ RAG pipeline (embed → Qdrant → rerank → LLM) | ✅ Done |
| Phase 3 | Orchestrator, LINE webhook, session memory | 🟡 Next |
| Phase 4 | Conversation history + LLM summarization | 🟡 Pending |
| Phase 5 | Troubleshooting agent (ReAct + tools) | 🟡 Pending |
| Phase 6 | Withdrawal diagnosis domain logic | 🟡 Pending |
| Phase 7 | Observability, evaluation, LangSmith | 🟡 Pending |
| Phase 8 | Real API clients, production hardening | 🟡 Pending |

---

## Root Files

| File | State | What's Inside |
|------|-------|---------------|
| `main.py` | ✅ | CLI entry point — `python main.py api\|gradio` |
| `requirements.txt` | ✅ | All dependencies pinned |
| `.env.example` | ✅ | All required env vars documented |
| `PLAN.md` | ✅ | 8-phase implementation plan |

---

## `interface/` — Entry Points

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `fastapi_app.py` | 🟡 | FastAPI app, `/health`, LINE webhook skeleton, HMAC-SHA256 validation | Phase 3: wire to orchestrator |
| `gradio_app.py` | ✅ | Full Gradio test UI wired to complete FAQ pipeline with `PipelineTrace` logging | — |

---

## `pipeline/` — Main Request Flow

| File | State | What's Inside | What's Missing |
|------|-------|---------------|----------------|
| `orchestrator.py` | 🟡 | `RequestContext` and `ResponseContext` dataclasses, `handle_message()` stub | Phase 3: full pipeline logic |
| `router.py` | ✅ | `Route` enum, `decide_route()` — template/troubleshooting/FAQ routing by intent + keywords | — |
| `safety.py` | ✅ | `IN_SCOPE_KEYWORDS`, `BLOCKED_PATTERNS`, `check_safety()` — scope filter with short-message bypass | — |
| `answer_generator.py` | ✅ | LLM call, `_score_grounding()` word-overlap heuristic, `_clean_answer()` strips preamble + related-questions boilerplate, `HANDOFF_THRESHOLD=0.25`, Thai/EN system prompts | — |
| `handoff.py` | 🟡 | `HandoffContext` dataclass, `build_handoff_context()` and `format_handoff_message()` stubs | Phase 3 |

---

## `rag/` — RAG / FAQ Retrieval Pipeline ✅ Complete

| File | State | What's Inside |
|------|-------|---------------|
| `embeddings.py` | ✅ | Lazy-load `distiluse-base-multilingual-cased-v2`, LRU cache for queries, batch encoding, `EMBEDDING_DIM=512` |
| `reranker.py` | ✅ | `BAAI/bge-reranker-base` CrossEncoder, sigmoid normalization, `threshold=0.3`, fallback to top_k |
| `query_cleaner.py` | ✅ | Thai-safe punctuation stripping, synonym normalization, `SYNONYM_MAP` |
| `retriever.py` | ✅ | Full pipeline: clean → embed → Qdrant search (top 10) → rerank (top 5) → `build_context()` |

---

## `agent/` — Troubleshooting Agent

### Core

| File | State | What's Missing |
|------|-------|----------------|
| `planner.py` | 🟡 | Phase 5: `create_react_agent` + `AgentExecutor` |
| `evidence.py` | 🟡 | Phase 5: parse tool JSONs, extract root cause |

### `agent/tools/` ✅ — Wired to Mocks

All 5 tools fully wired to mock clients via `USE_MOCK_APIS=true`.

| File | Covers |
|------|--------|
| `attendance.py` | Attendance history, absent/late days |
| `shift.py` | Work hours, shift assignment |
| `deduction.py` | Salary deduction breakdown |
| `employee_status.py` | Withdrawal eligibility, enrollment |
| `sync_schedule.py` | Last/next sync, failures |

### `agent/clients/mock/` ✅ — Fixture data for EMP001

### `agent/clients/` 🟡 — Real clients stub (`raise NotImplementedError("Phase 8")`)

---

## `memory/` — Session + Conversation Memory

| File | State | What's Missing |
|------|-------|----------------|
| `redis_client.py` | 🟡 | Phase 1: Redis connection with pooling |
| `session.py` | 🟡 | Phase 3: Redis CRUD (TTL=1800s) |
| `history.py` | 🟡 | Phase 3: Redis list push/load (TTL=7d, max 20 turns) |
| `summarizer.py` | 🟡 | Phase 4: LLM summarization at 15 turns |

---

## `llm/` — LLM + Language Utilities

| File | State | Notes |
|------|-------|-------|
| `client.py` | ✅ | `claude-3-haiku`, tenacity retry on rate limit, token logging |
| `intent.py` | 🟡 | Phase 2: keyword matching (partial — router handles simple intents) |
| `language.py` | ✅ | Thai Unicode detection (also in `utils/language.py`) |
| `templates.py` | ✅ | All 6 Thai + English templates: greeting, thanks, goodbye, frustrated, confused, unclear |
| `providers/anthropic.py` | ✅ | Anthropic SDK, `@retry` on `RateLimitError` |

---

## `utils/` — Utilities

| File | State | What's Inside |
|------|-------|---------------|
| `language.py` | ✅ | `detect_language()` — Thai Unicode regex |
| `pipeline_logger.py` | ✅ | `PipelineTrace` — writes `logs/faq_trace.log` (readable blocks) + `logs/faq_trace.jsonl` (machine-readable) |

---

## `domain/` — Business Logic

| File | State | What's Missing |
|------|-------|----------------|
| `withdraw_diagnosis.py` | 🟡 | Phase 6: `diagnose_withdrawal_failure()` rule engine |
| `withdraw_formatter.py` | 🟡 | Phase 6: `format_diagnosis()` — messages written for all 6 cases |

---

## `observability/` — Tracing & Metrics

| File | State | What's Missing |
|------|-------|----------------|
| `tracing.py` | 🟡 | Phase 7: LangSmith integration |
| `metrics.py` | 🟡 | Phase 7: metrics backend |

---

## `indexers/` — Offline Knowledge Pipeline ✅ Complete

| File | State | What's Inside |
|------|-------|---------------|
| `index_faq_csv.py` | ✅ | Embeds Context+Question, upserts to Qdrant with full payload |
| `merge_data.py` | ✅ | Merges public + company CSVs, deduplicates by question, handles bilingual columns |
| `inspect_qdrant.py` | ✅ | Lists collections with counts, shows sample records |

---

## `scripts/` — Dev Tools

| File | State | What's Inside |
|------|-------|---------------|
| `scripts/test_faq.py` | ✅ | Batch tester — runs 31 Thai questions, prints coverage table, writes to `logs/faq_trace.log` |

---

## `config/` — YAML Configuration

| File | State | What's Inside |
|------|-------|---------------|
| `tenants.yaml` | 📄 | HNS tenant: company_id, languages, LINE tokens, vector collections, feature flags |
| `incident_data.yaml` | 📄 | 3 active incidents: salary delay, maintenance window, iOS 17 login bug |

---

## `data/` — Knowledge Sources

| File | State | Rows | Content |
|------|-------|------|---------|
| `data/faqs/public_faq.csv` | 📄 | 9 | General Salary Hero Q&A in Thai |
| `data/company/hns/hns_company.csv` | 📄 | 73 | HNS-specific bilingual FAQ (TH/EN columns) |
| `data/merged/hns_th.csv` | 📄 | 73 | Merged + normalized Thai FAQ (Qdrant source) |

**Qdrant collections:**
- `hns_th` — 73 documents indexed ✅

---

## `tests/` — Test Suite

### Unit Tests

| File | State | Runnable? |
|------|-------|-----------|
| `test_query_cleaner.py` | 🧪 | ✅ All 15 pass |
| `test_embeddings.py` | 🧪 | ✅ All 4 pass (mocked model) |
| `test_intent.py` | 🧪 | After Phase 2 |
| `test_language.py` | 🧪 | ✅ `test_is_thai_*` pass |
| `test_router.py` | 🧪 | ✅ After Phase 3 |
| `test_safety.py` | 🧪 | After Phase 3 |
| `test_reranker.py` | 🧪 | ✅ `TestSigmoid.*` passes |
| `test_withdraw_diagnosis.py` | 🧪 | ✅ `TestHelperFunctions.*` passes |

### Integration Tests

| File | State | Runnable? |
|------|-------|-----------|
| `test_agent_tools.py` | 🧪 | ✅ All 5 tool tests pass (mock clients) |
| `test_rag_pipeline.py` | 🧪 | ✅ Runnable (Qdrant populated) |

---

## FAQ Pipeline — Test Results (2026-04-01)

Run: `PYTHONPATH=. python scripts/test_faq.py`

```
Total: 31  |  Answered: 30  |  Escalated (no data): 1
Coverage: 97%
```

**Only gap:** "หัวหน้าตั้งกะงานให้แล้วแต่ยอดไม่ขึ้น" — needs a row added to `hns_company.csv`

---

## What to Run Now

```bash
# Start Gradio test UI
PYTHONPATH=. python main.py gradio

# Run full FAQ test (31 questions)
PYTHONPATH=. python scripts/test_faq.py

# Index FAQs (after CSV changes)
PYTHONPATH=. python indexers/merge_data.py --company hns --language th
PYTHONPATH=. python indexers/index_faq_csv.py --file data/merged/hns_th.csv --company hns --language th

# Check Qdrant
PYTHONPATH=. python indexers/inspect_qdrant.py

# Run unit tests
pytest tests/unit/ -v
```

---

## Phase 3 Starting Point

The next phase is **Phase 3: Orchestrator + LINE Webhook**.
Start with these files in order:

1. `memory/redis_client.py` — Redis singleton + health check
2. `memory/session.py` — session CRUD (TTL 30 min)
3. `memory/history.py` — conversation history (TTL 7 days)
4. `pipeline/orchestrator.py` — wire router → safety → retrieve → generate
5. `interface/fastapi_app.py` — complete LINE webhook with HMAC validation
