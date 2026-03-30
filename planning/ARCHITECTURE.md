# CS Chatbot Agent — Architecture Overview

## System Overview

An intelligent Customer Support chatbot for **Salary Hero** that handles employee inquiries via LINE messaging. The system uses a **Router-based architecture** to direct queries to either a **RAG knowledge retrieval** pipeline or a **Troubleshooting Agent** with specialized tools, with built-in **safety checks**, **quality grounding**, and **human handoff** capabilities.

---

## High-Level Flow

```
User → Chat Input → Receive Session ID
                          │
                    Load Recent Messages
                          │
                   ┌──────▼──────┐
                   │ History Too  │───Yes──→ Summarize Older Messages ─┐
                   │   Long?     │                                     │
                   └──────┬──────┘                                     │
                          │ No                                         │
                          ▼                                            │
                   Build Request Context ◄─────────────────────────────┘
                          │
                    Detect Language
                          │
                    Detect Intent
                          │
                 Safety And Policy Check
                          │
                    ┌─────▼─────┐
                    │  Router   │
                    └─────┬─────┘
              ┌───────────┼───────────┐
              │           │           │
           FAQ Path   Escalated   Routing Info
              │        Path          │
              ▼           ▼          ▼
     LangChain      Troubleshooting   Answer
     Retrieval        Agent         Generation
```

---

## 1. Request Entry

The entry point for all user interactions.

| Step | Description |
|------|-------------|
| **Chat Input** | User sends a message via LINE |
| **Receive Session ID** | Retrieve or create a session for the user |
| **Load Recent Messages** | Fetch conversation history from Redis |
| **History Too Long?** | Check if chat history exceeds context window |
| **Summarize Older Messages** | If history is too long, compress older turns into a summary |
| **Build Request Context** | Combine user message + recent history + summary into a structured request |
| **Detect Language** | Identify message language (Thai / English) |
| **Detect Intent** | Classify user intent (FAQ, troubleshooting, greeting, etc.) |
| **Safety And Policy Check** | Filter harmful, off-topic, or policy-violating content |

---

## 2. Router

The Router analyzes the processed request and directs it to the appropriate handler.

```
                    ┌──────────┐
                    │  Router  │
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       FAQ Path     Escalated      Existing Info
          │           Path              │
          ▼              ▼              ▼
   LangChain       Troubleshooting   Answer
   Retrieval         Agent         Generation
```

| Route | Trigger | Destination |
|-------|---------|-------------|
| **FAQ** | Knowledge-based questions | LangChain Retrieval pipeline |
| **Escalated** | Complex employee-specific issues | Troubleshooting Agent |
| **Existing Info** | Already has context/routing info | Direct to Answer Generation |

---

## 3. LangChain Retrieval (RAG Pipeline)

Handles FAQ and knowledge-based queries using vector search. This is the **current production path** — the existing codebase implements this pipeline end-to-end.

```
Prepare Search Query
        │
   Query Embedding (cached, LRU 500 entries)
        │
   Vector Search (Qdrant top 10)
        │
  ┌─────▼─────┐
  │ Good Match?│───Yes──→ Build Context
  └─────┬──────┘
        │ No
   Rerank Results (BGE top 5, threshold 0.3)
        │
  Build Context
```

| Step | Description |
|------|-------------|
| **Prepare Search Query** | Clean and optimize the user query — lowercase, collapse spaces, remove punctuation, handle Thai/EN synonyms (`clean_questions.py`) |
| **Query Embedding** | Convert query to 384-dim vector via SentenceTransformer (`distiluse-base-multilingual-cased-v2`). Cached with 500-entry LRU (`retriever.py`) |
| **Vector Search** | Search Qdrant (primary) or Pinecone (fallback) for top 10 matching documents. Collection: `{company}_{lang}` |
| **Good Match?** | Evaluate if top results are above confidence threshold |
| **Rerank Results** | BGE Reranker (`BAAI/bge-reranker-base`) — sigmoid scoring, filters scores < 0.3, returns top 5 (`bge_reranker.py`) |
| **Build Context** | Assemble reranked documents into LLM-ready context. Inject active incidents if applicable (`retriever.py`) |

### 3.1 Orchestration (chains.py)

The main orchestrator `load_chat_chain()` coordinates the full FAQ request lifecycle:

```
Language Detection → Intent Classification → Search → Rerank → LLM → Memory
```

### 3.2 Modules Involved

| Module | Role | Key Functions |
|--------|------|---------------|
| `core/chains.py` | Main orchestrator | `load_chat_chain()` — full request lifecycle with profiling |
| `core/retriever.py` | RAG pipeline | `get_embedding_cached()`, `query_vector_store_fast()`, `parallel_processing()`, `build_optimized_context()`, `build_thai_summary()` |
| `core/embeddings.py` | Embedding generation | `SentenceTransformerEmbeddings` — `embed_documents()` (batch 16), `embed_query()` (single) |
| `core/bge_reranker.py` | Result reranking | `rerank_bge()` — sigmoid scoring, top-K above threshold (default 0.3) |
| `core/llm.py` | Claude LLM wrapper | `CustomLLM` — dynamic token management, timeout/rate-limit handling, language-aware fallbacks |
| `core/thai_summary.py` | Thai summarization | `build_thai_summary()` (LLM-based), `_fallback_summary()` (rule-based). Truncates Q: 300 chars, A: 600 chars |
| `utils/intent_detector.py` | Intent classification | `detect_intent()` — keyword-based (greeting, thanks, goodbye, frustrated, confused, question) |
| `utils/clean_questions.py` | Text normalization | `clean_and_standardize_question()` — Thai/EN synonyms, punctuation, whitespace |
| `utils/language.py` | Language detection | `detect_language()` — currently hardcoded to `'th'` (TODO) |
| `utils/incidents.py` | Incident loader | `load_active_incidents()` — from YAML, filtered by tenant & date range |
| `utils/templates.py` | Response templates | `ENGLISH_TEMPLATES`, `THAI_TEMPLATES` — for greeting, thanks, frustrated, confused, goodbye, unclear |

### 3.3 Intent Routing (Before RAG)

Simple intents are handled with template responses, bypassing the full RAG pipeline:

| Intent | Handler | Example |
|--------|---------|---------|
| `greeting` | Template reply | "สวัสดีค่ะ" / "Hello!" |
| `thanks` | Template reply | "ยินดีค่ะ" / "You're welcome!" |
| `goodbye` | Template reply | "ลาก่อนค่ะ" |
| `frustrated` | Empathy template | Acknowledges frustration, offers help |
| `confused` | Clarification template | Asks user to rephrase |
| `unclear` | Clarification template | Asks for more details |
| `question` | **→ RAG Pipeline** | Proceeds to vector search |

### 3.4 Domain-Specific Logic

Specialized rule engines that run alongside or instead of RAG for specific topics:

| Module | Purpose | Details |
|--------|---------|---------|
| `core/withdraw_diagnosis.py` | Zero-withdrawal diagnosis | 6-case rule engine for zero-balance scenarios (blocked, blacklist, limit, cooldown, etc.) |
| `core/withdraw_flow.py` | Diagnosis formatter | `build_withdraw_diagnosis_answer()` — formats reason + next steps (Thai/EN) |

### 3.5 Knowledge Data Format

**CSV columns:** `Context | Question | Answer | source_type | company_id | incident | tags | followup_questions`

| Source File | Content | Rows |
|-------------|---------|------|
| `data/faqs/public_faq.csv` | General Salary Hero Q&A | 9 |
| `data/faqs/public_incident.csv` | Incident template | empty |
| `data/company/hns/hns_company.csv` | HNS-specific FAQs (withdrawal hours, conditions, transfer timing) | — |
| `config/incident_data.yaml` | Active incidents (salary delays, maintenance, login issues, system upgrades) | 6 |

### 3.6 Vector DB Schema

```
Collection: {company_id}_{language}
├─ Vectors: 384-dimensional (SentenceTransformer)
├─ Metadata:
│   ├─ context         (question category)
│   ├─ question        (original question)
│   ├─ answer          (FAQ answer)
│   ├─ source_type     ("faq" | "incident" | "company")
│   ├─ company_id      (tenant identifier)
│   ├─ incident        (optional incident reference)
│   ├─ tags            (list of strings)
│   └─ followup_questions (list of strings)
└─ Backend: Qdrant (primary) or Pinecone (fallback)
```

### 3.7 External Services (FAQ Path)

| Service | Purpose | Env Vars |
|---------|---------|----------|
| Anthropic Claude (`claude-3-haiku`) | LLM generation + Thai summarization | `ANTHROPIC_API_KEY` |
| Qdrant | Vector search (primary) | `QDRANT_HOST`, `QDRANT_API_KEY` |
| Pinecone | Vector search (fallback) | `PINECONE_API_KEY` |
| Redis | Memory (7-day TTL) + Session (30-min TTL) | `REDIS_URL` |

### 3.8 Current FAQ Path Limitations

| Issue | Details |
|-------|---------|
| Language detection hardcoded | `language.py` always returns `'th'` |
| Mock withdrawal data | `withdraw_diagnosis.py` uses mock data, no real API |
| Fuzzy matching disabled | `friendly_responses.py` fuzzy matching commented out |
| Single tenant only | Only `hns` configured, multi-tenancy not fully implemented |
| Dead code | `router.py` placeholder, `query_classifier.py` SetFit stub |
| No test suite | No automated tests |
| Heavy memory footprint | Embedding model loaded in-process |

---

## 4. Troubleshooting Agent

Handles escalated, employee-specific issues using specialized tools.

```
                  ┌──────────────┐
                  │ Tool Planner │
                  └──────┬───────┘
                         │
        ┌────────┬───────┼────────┬─────────────┐
        │        │       │        │             │
        ▼        ▼       ▼        ▼             ▼
  Attendance   Shift  Deduction  Employee   Sync Schedule
    Tool       Tool    Tool     Status Tool     Tool
        │        │       │        │             │
        └────────┴───────┼────────┴─────────────┘
                         │
                   Build Evidence
                         │
               Build Diagnostic Context
```

| Component | Description |
|-----------|-------------|
| **Tool Planner** | Analyzes the issue and determines which tools to invoke |
| **Attendance Tool** | Query attendance records |
| **Shift Tool** | Look up shift schedules and assignments |
| **Deduction Tool** | Check salary deductions and calculations |
| **Employee Status Tool** | Verify employee status, eligibility, enrollment |
| **Sync Schedule Tool** | Check payroll sync and schedule timing |
| **Build Evidence** | Collect results from all invoked tools |
| **Build Diagnostic Context** | Synthesize evidence into a diagnostic summary for the LLM |

---

## 5. Answer Generation

Produces the final response with quality controls.

```
              ┌──────────────────┐
              │ Answer Generation│
              └────────┬─────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
   Template Reply     LLM     Ask Clarifying
                       │        Questions
                       ▼
              Check Quality And
                 Grounding
                       │
               ┌───────▼───────┐
               │Low Confidence?│───Yes──→ Human Handoff
               └───────┬───────┘
                       │ No
                  Final Answer
                       │
           Save Conversation History
                  To Redis
```

| Component | Description |
|-----------|-------------|
| **Template Reply** | Pre-written responses for known intents (greetings, thanks, etc.) |
| **LLM** | Claude generates a response from retrieved context / diagnostic data |
| **Ask Clarifying Questions** | Request more info if the query is ambiguous |
| **Check Quality And Grounding** | Verify the response is accurate, grounded in retrieved data, and policy-compliant |
| **Low Confidence?** | If quality check fails → escalate to human |
| **Human Handoff** | Transfer conversation to a live CS agent |
| **Final Answer** | Deliver the validated response to the user |
| **Save Conversation History To Redis** | Persist the exchange for future context |

---

## 6. Memory & History Management

Redis-backed memory with LangChain integration.

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│ Redis Recent Chat    │────▶│ LangChain Short Term │────▶│ Redis Conversation   │
│ History              │     │ Memory               │     │ Summary              │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

| Component | Description |
|-----------|-------------|
| **Redis Recent Chat History** | Stores raw recent messages (last N turns) |
| **LangChain Short Term Memory** | Active working memory used during request processing |
| **Redis Conversation Summary** | Compressed summaries of older conversations for long-term context |

**Strategy:** Recent messages are kept in full. When history grows too long, older messages are summarized (via LLM) and stored as a conversation summary, keeping the context window manageable.

---

## 7. Offline Knowledge Pipeline

Ingests and indexes FAQ/knowledge documents for vector search.

```
Docs / PDFs / CSV
       │
  Extract Text
       │
 Clean And Normalize
       │
   Chunk Text
       │
 Create Embeddings
       │
Vector DB (Pinecone or Qdrant)
```

| Step | Description |
|------|-------------|
| **Docs / PDFs / CSV** | Raw knowledge sources (FAQ sheets, policy docs, company data) |
| **Extract Text** | Parse content from various file formats |
| **Clean And Normalize** | Text normalization (Thai/EN synonyms, whitespace, punctuation) |
| **Chunk Text** | Split into appropriately sized chunks for embedding |
| **Create Embeddings** | Generate vector embeddings (SentenceTransformer) |
| **Vector DB** | Store in Qdrant (primary) or Pinecone (fallback) for retrieval |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| LLM | Anthropic Claude |
| Embeddings | SentenceTransformer (multilingual) |
| Reranking | BGE Reranker (BAAI/bge-reranker-base) |
| Vector DB | Qdrant (primary) / Pinecone (fallback) |
| Memory | Redis + LangChain Memory |
| API | FastAPI (LINE webhook) |
| Messaging | LINE Messaging API |
| Agent Framework | LangChain (tools, memory, chains) |
| Language | Python 3.11 |
| Deployment | Railway / Render |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Router-based architecture** | Separates FAQ retrieval from complex troubleshooting, allowing specialized handling for each |
| **Troubleshooting Agent with tools** | Employee-specific issues require querying live data (attendance, shifts, deductions), not just FAQ search |
| **LangChain memory with summarization** | Maintains long conversation context without exceeding LLM token limits |
| **Safety And Policy Check** | Prevents the bot from responding to harmful, off-topic, or policy-violating queries |
| **Quality grounding check** | Ensures LLM responses are factually supported by retrieved data before delivery |
| **Human handoff** | Graceful escalation when the bot lacks confidence, preserving user trust |
| **Offline knowledge pipeline** | Decouples document ingestion from real-time serving for reliability and performance |
