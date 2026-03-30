# CS Chatbot Platform — Project Summary

## Overview

Customer Support Chatbot for **Salary Hero** (earned wage access / financial wellness platform).  
Handles employee FAQ queries via **LINE messaging** in **Thai + English** using a **RAG** (Retrieval-Augmented Generation) pipeline.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Anthropic Claude (claude-3-haiku-20240307) |
| Embeddings | SentenceTransformer (distiluse-base-multilingual-cased-v2) |
| Reranking | BGE Reranker (BAAI/bge-reranker-base) |
| Vector DB | Qdrant (primary), Pinecone (fallback) |
| Memory / Session | Redis (7-day memory TTL, 30-min session TTL) |
| API | FastAPI (LINE webhook) |
| Test UI | Gradio |
| Deployment | Railway / Render |
| Language | Python 3.11 |

---

## Core Flow

```
LINE Message → FastAPI Webhook (HMAC signature verified)
  → Language Detection (currently hardcoded to Thai)
  → Intent Detection (greeting / thanks / question / frustrated / etc.)
  → IF simple intent → template response
  → ELSE RAG pipeline:
      1. Embed query (cached, 500-entry LRU limit)
      2. Vector search in Qdrant (top 10 results)
      3. BGE rerank (top 5, score threshold 0.3)
      4. Build context from reranked docs
      5. Claude LLM generates answer
      6. Thai summary (LLM-based with rule-based fallback)
      7. Save to Redis memory + session
  → Reply via LINE Messaging API
```

---

## Project Structure

```
cs-chatbot-platform/
├── main.py                    # Entry point (CLI / dev)
├── requirements.txt           # Python dependencies
├── runtime.txt                # Python 3.11.9
├── railway.json               # Railway deployment config
├── render.yaml                # Render deployment config
│
├── config/
│   ├── tenants.yaml           # Tenant → vector DB namespace mapping
│   └── incident_data.yaml     # Active incident definitions (Thai/EN)
│
├── core/
│   ├── llm.py                 # Claude wrapper (token mgmt, timeouts, fallbacks)
│   ├── embeddings.py          # SentenceTransformer wrapper (batch embed)
│   ├── retriever.py           # RAG pipeline: cache → vector search → context
│   ├── chains.py              # Main orchestrator: lang → intent → search → rerank → LLM → memory
│   ├── bge_reranker.py        # BGE sigmoid-based reranking
│   ├── query_classifier.py    # SetFit intent classifier (stub)
│   ├── redis_client.py        # Redis connection factory
│   ├── redis_memory.py        # Chat memory storage (7-day TTL)
│   ├── redis_sessions.py      # Session management (30-min TTL)
│   ├── thai_summary.py        # Thai Q&A summarization via Claude
│   ├── withdraw_diagnosis.py  # Zero-withdrawal rule engine (6 cases)
│   └── withdraw_flow.py       # Withdrawal diagnosis formatter
│
├── interface/
│   ├── fastapi_app.py         # LINE webhook: signature verify, text/sticker/image, quick replies, flex banners, bot↔human mode
│   ├── gradio_app.py          # Test UI with tenant selector
│   └── router.py              # Placeholder tenant routing (unused)
│
├── utils/
│   ├── intent_detector.py     # Keyword-based intent classification + template responses
│   ├── friendly_responses.py  # Canned responses for greetings/thanks/goodbye
│   ├── clean_questions.py     # Text normalization (Thai/EN synonyms, punctuation)
│   ├── language.py            # Language detection (hardcoded to 'th')
│   ├── incidents.py           # Active incident loader from YAML (date-filtered)
│   └── templates.py           # Pre-written Thai/English response templates
│
├── indexers/
│   ├── index_faq_csv.py       # Main indexer: CSV → embed → upsert to Qdrant/Pinecone
│   ├── merge_data.py          # Merge public + company FAQs → per-language CSVs
│   ├── embed_faqs.py          # Legacy Pinecone indexer
│   ├── inspect_qdrant.py      # Debug: list collections, sample vectors
│   └── delete_namespace.py    # Pinecone namespace cleanup
│
├── data/
│   ├── faqs/
│   │   ├── public_faq.csv         # General Salary Hero Q&A
│   │   └── public_incident.csv    # Incident template (empty)
│   ├── company/
│   │   └── hns/
│   │       └── hns_company.csv    # HNS-specific FAQs
│   └── merged/
│       └── hns_th.csv             # Merged output (public + HNS, Thai)
│
├── scripts/
│   ├── clear_redis_chat_data.py   # Bulk delete Redis chat keys
│   └── debug_redis_memory_all.py  # Dump all memory records (JSON)
│
└── templates/                     # (empty)
```

---

## Module Details

### core/

| Module | Purpose | Key Functions |
|---|---|---|
| `llm.py` | Claude LLM wrapper | `CustomLLM` class — dynamic token management, detailed logging, timeout/rate-limit handling, language-aware fallbacks |
| `embeddings.py` | Embedding generation | `SentenceTransformerEmbeddings` — `embed_documents()` (batch, 16 at a time), `embed_query()` (single) |
| `retriever.py` | RAG retrieval pipeline | `get_embedding_cached()`, `query_vector_store_fast()`, `parallel_processing()`, `detect_employee_info_submission()`, `build_optimized_context()`, `build_thai_summary()` |
| `chains.py` | Main conversation chain | `load_chat_chain()` — orchestrates full request lifecycle with profiling |
| `bge_reranker.py` | Result reranking | `rerank_bge()` — sigmoid scoring, returns top-K above threshold (default 0.3) |
| `query_classifier.py` | Intent classification | SetFit-based classifier (stub) — returns: greeting, thanks, unclear, chitchat, faq, complex |
| `redis_client.py` | Redis connection | `get_redis_client()` — initializes from `REDIS_URL` env var |
| `redis_memory.py` | Chat memory | `save_memory()`, `get_recent_memory()` — key: `chat:memory:{tenant}:{user}:{lang}`, 7-day TTL |
| `redis_sessions.py` | Session state | `get_session()`, `save_session()`, `clear_session()` — key: `chat:session:{tenant}:{user}`, 30-min TTL |
| `thai_summary.py` | Thai summarization | `build_thai_summary()` (LLM-based), `_fallback_summary()` (rule-based). Truncates inputs (300 chars Q, 600 chars A) |
| `withdraw_diagnosis.py` | Domain logic | `diagnose_zero_withdraw()` — 6-case rule engine for zero-balance scenarios |
| `withdraw_flow.py` | Diagnosis formatter | `build_withdraw_diagnosis_answer()` — formats reason + next steps (Thai/EN) |

### interface/

| Module | Purpose | Key Details |
|---|---|---|
| `fastapi_app.py` | LINE webhook (production) | `POST /webhook` — HMAC signature verification, text/sticker/image handling, quick replies, flex banners, async HTTP to LINE API, bot↔human mode switching. `GET /` — health check |
| `gradio_app.py` | Test UI | `run_ui()` — multi-tenant chatbot UI with tenant selector, message history, language auto-detection. Port 7860 |
| `router.py` | Tenant routing | `load_tenant_config()` — hardcoded mappings (dead code, replaced by `tenants.yaml`) |

### utils/

| Module | Purpose | Key Details |
|---|---|---|
| `intent_detector.py` | Intent classification | `detect_intent()` — keyword-based (greeting, thanks, goodbye, unclear, frustrated, confused, question). `get_template_response()`, `enhance_response_with_personality()`, `get_intent_guidance()` |
| `friendly_responses.py` | Canned replies | `friendly_reply()` — detects greetings/thanks/goodbye/yes/no → returns preset responses (Thai/EN). Fuzzy matching disabled |
| `clean_questions.py` | Text normalization | `clean_and_standardize_question()` — lowercase, collapse spaces, remove punctuation, handle Thai/EN synonyms |
| `language.py` | Language detection | `detect_language()` — **hardcoded to return `'th'`** (TODO: implement actual detection) |
| `incidents.py` | Incident loader | `load_active_incidents()` — loads from YAML, filters by tenant & date range |
| `templates.py` | Response templates | `ENGLISH_TEMPLATES`, `THAI_TEMPLATES` — for greeting, thanks, frustrated, confused, goodbye, unclear |

### indexers/

| Module | Purpose | Key Details |
|---|---|---|
| `index_faq_csv.py` | Main indexer | CSV → embed → upsert to Qdrant/Pinecone. Metadata: context, question, answer, source_type, company_id, incident. Supports `--replace` flag |
| `merge_data.py` | Data pipeline | Merges public FAQ + incidents + company FAQs → `{company}_{lang}.csv`. Applies question cleaning |
| `embed_faqs.py` | Legacy indexer | Pinecone-specific. Reads FAQ CSV → embeds → upserts with EN/TH namespaces |
| `inspect_qdrant.py` | Debug tool | CLI: list collections, vector counts, dimensions, sample payloads |
| `delete_namespace.py` | Cleanup tool | `delete_vectors_by_namespace()` — wipes a Pinecone namespace |

---

## Data Format

**CSV columns:** `Context | Question | Answer | source_type | company_id | incident | tags | followup_questions`

**Sources:**
- `public_faq.csv` — General Salary Hero Q&A (9 rows)
- `public_incident.csv` — Incident template (empty)
- `hns_company.csv` — HNS-specific FAQs (withdrawal hours, conditions, transfer timing)
- `incident_data.yaml` — 6 incidents (salary delays, maintenance, login issues, system upgrades) with severity levels

---

## External Services

| Service | Purpose | Env Var |
|---|---|---|
| Anthropic Claude | LLM generation, Thai summarization | `ANTHROPIC_API_KEY` |
| Qdrant | Vector database (primary) | `QDRANT_HOST`, `QDRANT_API_KEY` |
| Pinecone | Vector database (fallback) | `PINECONE_API_KEY` |
| Redis | Session & memory storage | `REDIS_URL` |
| LINE Messaging API | Webhook, replies, push messages | `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET` |

---

## Environment Variables

```env
ANTHROPIC_API_KEY              # Claude API key
QDRANT_HOST                    # Qdrant cloud URL
QDRANT_API_KEY                 # Qdrant API key
PINECONE_API_KEY               # Pinecone API key (if using Pinecone)
VECTOR_BACKEND                 # "qdrant" or "pinecone"
REDIS_URL                      # Redis connection URL
LINE_CHANNEL_ACCESS_TOKEN      # LINE messaging token
LINE_CHANNEL_SECRET            # LINE webhook signing secret
ENABLE_EMBEDDING_CACHE         # true/false (default: true)
ENABLE_PARALLEL_PROCESSING     # true/false (default: true)
```

---

## Key Features

1. **RAG Pipeline** — embedding cache (500-entry LRU) → vector search → BGE quality-aware reranking
2. **Bilingual** — Thai + English support (language detection is TODO)
3. **Intent Routing** — keyword-based classification → template responses for non-FAQ intents
4. **Conversation Memory** — Redis long-term (7d) + session context (30m)
5. **Thai NLP** — native Thai summarization via Claude with rule-based fallback
6. **Human Escalation** — bot↔human mode switching with LINE flex banners
7. **Domain Logic** — zero-withdrawal diagnosis rule engine (6 cases)
8. **Multi-tenant Ready** — tenant config in YAML (currently only `hns`)
9. **Incident System** — date-filtered active incidents from YAML config
10. **Dual Interface** — FastAPI (production LINE webhook) + Gradio (testing)

---

## Known Issues / Technical Debt

1. `language.py` — language detection hardcoded to `'th'`
2. `withdraw_diagnosis.py` — uses mock data, no real API integration
3. `friendly_responses.py` — fuzzy matching commented out / disabled
4. Single tenant only (`hns`), multi-tenancy not fully implemented
5. `router.py` — dead placeholder code
6. `query_classifier.py` — SetFit classifier is a stub
7. Dual vector DB (Qdrant + Pinecone) adds unnecessary complexity
8. No test suite
9. Embedding model loaded in-process (heavy memory footprint)
10. No structured logging or monitoring/alerting

---

## Deployment

| Platform | Build | Run |
|---|---|---|
| Railway | `pip install -r requirements.txt` | Gradio on port 8000 |
| Render | Python 3.11 + env vars | FastAPI + Gradio |
| Local | `pip install -r requirements.txt` | FastAPI :8000, Gradio :7860 |
