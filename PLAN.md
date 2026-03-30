# CS Chatbot Agent — Implementation Plan

## Overview

This plan is organized into 8 phases, ordered by dependency.
Each phase builds on the previous and produces a testable milestone.

---

## Phase 1: Foundation & Infrastructure
**Goal:** Project boots, connects to Redis and LLM, LINE webhook accepts requests.

### Tasks
- [ ] Set up `requirements.txt` and virtual environment
- [ ] Load environment variables and validate on startup
- [ ] Implement `memory/redis_client.py` — Redis singleton with connection health check
- [ ] Implement `llm/client.py` — Claude wrapper with timeout, retry, rate-limit handling
- [ ] Implement `interface/fastapi_app.py` skeleton — LINE webhook with HMAC-SHA256 signature validation (no response logic yet)
- [ ] Implement `main.py` — CLI entry point (`python main.py api|gradio`)
- [ ] Implement `config/` loaders — parse `tenants.yaml` and `incident_data.yaml` at startup

### Milestone
`python main.py api` starts, LINE webhook validates signatures, Redis and LLM connections confirmed.

---

## Phase 2: RAG Pipeline (FAQ Path)
**Goal:** Given a user query, retrieve relevant FAQs and generate an answer.

### Tasks
- [ ] Implement `rag/embeddings.py` — SentenceTransformer wrapper with LRU cache (500 entries)
- [ ] Implement `rag/query_cleaner.py` — Thai/EN text normalization (lowercase, punctuation, synonyms)
- [ ] Implement `rag/reranker.py` — BGE reranker with sigmoid scoring, filter threshold 0.3
- [ ] Implement `rag/retriever.py` — full pipeline: embed → Qdrant search (top 10) → rerank (top 5) → build context
- [ ] Implement `llm/templates.py` — Thai + English response templates for all intent types
- [ ] Implement `llm/intent.py` — keyword-based intent detection (greeting, thanks, goodbye, frustrated, confused, unclear, question)
- [ ] Implement `llm/language.py` — language detection (Thai / English) using PyThaiNLP or langdetect
- [ ] Implement `indexers/index_faq_csv.py` — index FAQ CSVs into Qdrant
- [ ] Index `data/faqs/public_faq.csv` and `data/company/hns/hns_company.csv`

### Milestone
`python indexers/index_faq_csv.py` populates Qdrant. Direct call to `retriever.py` returns ranked results for a Thai/EN test query.

---

## Phase 3: Pipeline Orchestration (End-to-End FAQ)
**Goal:** Full request flow from LINE message to FAQ response.

### Tasks
- [ ] Implement `memory/session.py` — create/get/expire sessions (30-min TTL)
- [ ] Implement `memory/history.py` — store/load chat history per user (7-day TTL, last N turns)
- [ ] Implement `pipeline/safety.py` — filter harmful, off-topic, or policy-violating content
- [ ] Implement `pipeline/router.py` — route to `faq | troubleshooting | direct` based on intent + classifier
- [ ] Implement `pipeline/answer_generator.py` — LLM generation + grounding score (0–1) + human handoff trigger
- [ ] Implement `pipeline/handoff.py` — build warm handoff context (conversation summary + issue + diagnostic)
- [ ] Implement `pipeline/orchestrator.py` — full flow: session → history → language → intent → safety → route → answer → save
- [ ] Wire `interface/fastapi_app.py` to orchestrator — end-to-end LINE message handling
- [ ] Implement `interface/gradio_app.py` — test UI for local development

### Milestone
Send a Thai/English FAQ question via Gradio → get a grounded answer. Human handoff triggers on low-confidence response.

---

## Phase 4: Memory & Context Management
**Goal:** Bot remembers conversation history across turns and compresses long histories.

### Tasks
- [ ] Implement `memory/summarizer.py` — LLM-based compression of older turns into a summary
- [ ] Update `pipeline/orchestrator.py` — detect history-too-long, trigger summarization, rebuild context
- [ ] Add LangChain `ConversationSummaryBufferMemory` integration
- [ ] Test multi-turn conversation with context retention

### Milestone
After 10+ turns, history is automatically summarized. Follow-up questions use correct prior context.

---

## Phase 5: Troubleshooting Agent
**Goal:** Route employee-specific issues to a LangChain ReAct agent with mock API tools.

### Tasks
- [ ] Implement `agent/clients/base.py` — abstract interfaces for all 5 API clients
- [ ] Implement all mock clients in `agent/clients/mock/` — return realistic fixture data
- [ ] Implement `agent/tools/attendance.py` — `@tool` wrapping attendance client
- [ ] Implement `agent/tools/shift.py` — `@tool` wrapping shift client
- [ ] Implement `agent/tools/deduction.py` — `@tool` wrapping deduction client
- [ ] Implement `agent/tools/employee_status.py` — `@tool` wrapping employee status client
- [ ] Implement `agent/tools/sync_schedule.py` — `@tool` wrapping sync schedule client
- [ ] Implement `agent/planner.py` — LangChain `AgentExecutor` (ReAct, `max_iterations=10`)
- [ ] Implement `agent/evidence.py` — collect tool outputs, build diagnostic context summary
- [ ] Update `pipeline/router.py` — detect troubleshooting intent and route to agent
- [ ] Update `pipeline/orchestrator.py` — handle agent path, pass diagnostic context to answer generator

### Milestone
Send "ทำไมถอนเงินไม่ได้" (why can't I withdraw) → agent selects correct tools, builds diagnosis, returns answer with evidence.

---

## Phase 6: Domain Logic
**Goal:** Handle Salary Hero-specific withdrawal diagnosis without API calls.

### Tasks
- [ ] Implement `domain/withdraw_diagnosis.py` — 6-case rule engine (blocked, blacklist, limit, cooldown, enrollment, sync)
- [ ] Implement `domain/withdraw_formatter.py` — format diagnosis result into Thai/EN response with next steps
- [ ] Integrate with `pipeline/router.py` — detect withdrawal queries and route to domain logic before RAG

### Milestone
Withdrawal-related queries return rule-based diagnosis with clear next steps in Thai and English.

---

## Phase 7: Observability & Evaluation
**Goal:** See what the bot is doing in production and measure quality.

### Tasks
- [ ] Implement `observability/tracing.py` — LangSmith (or Langfuse) integration for all LLM + agent calls
- [ ] Implement `observability/metrics.py` — track token cost, latency, escalation rate, error rate per tenant
- [ ] Implement `evaluation/rag_eval.py` — offline metrics: context precision, recall, faithfulness, answer relevance
- [ ] Implement `evaluation/agent_eval.py` — tool selection accuracy, loop count, hallucination rate
- [ ] Build `evaluation/datasets/rag_test_cases.json` — 20+ Thai/EN test cases with expected answers
- [ ] Build `evaluation/datasets/agent_test_cases.json` — 10+ troubleshooting scenarios with expected tool calls
- [ ] Add structured logging throughout pipeline (request ID, tenant, path taken, latency, grounding score)

### Milestone
Every request produces a LangSmith trace. Weekly eval run reports retrieval quality and agent accuracy.

---

## Phase 8: Production Readiness
**Goal:** Multi-tenant, real APIs, full test suite, deployable.

### Tasks
- [ ] Implement real API clients in `agent/clients/` — replace mocks with HTTP calls to internal HR APIs
- [ ] Fix `llm/language.py` — real language detection (remove hardcoded `'th'`)
- [ ] Implement multi-tenancy — tenant ID propagation through entire pipeline, per-tenant Qdrant collections
- [ ] Add second tenant config to `config/tenants.yaml` and test isolation
- [ ] Write unit tests for all `tests/unit/` stubs
- [ ] Write integration tests for all `tests/integration/` stubs
- [ ] Add rate limiting + idempotency key handling in `interface/fastapi_app.py`
- [ ] Add `indexers/merge_data.py` and `indexers/inspect_qdrant.py`
- [ ] Set up deployment config (Railway / Render) with all required env vars
- [ ] Load test with concurrent LINE users

### Milestone
Multi-tenant deployment passing all tests. Real HR API data. Production monitoring live.

---

## Dependency Order

```
Phase 1 (Foundation)
    └── Phase 2 (RAG Pipeline)
            └── Phase 3 (Orchestration) ──── Phase 4 (Memory)
                        └── Phase 5 (Agent)
                        └── Phase 6 (Domain)
                                    └── Phase 7 (Observability)
                                                └── Phase 8 (Production)
```

---

## Current Status

| Phase | Status |
|-------|--------|
| Phase 1 — Foundation | Not started |
| Phase 2 — RAG Pipeline | Not started |
| Phase 3 — Orchestration | Not started |
| Phase 4 — Memory | Not started |
| Phase 5 — Troubleshooting Agent | Not started |
| Phase 6 — Domain Logic | Not started |
| Phase 7 — Observability | Not started |
| Phase 8 — Production Readiness | Not started |
