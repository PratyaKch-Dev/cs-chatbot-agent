# CS Chatbot Agent — Claude Code Guidelines

## Session Resume
If `.claude/last_compact_summary.md` exists, read it silently at session start to restore context. Do not re-read project files unless the task requires it.

## Project

RAG-powered Customer Support chatbot for Salary Hero. Serves LINE messaging users in Thai + English.

## Architecture

See `ARCHITECTURE.md` for full details.

- **Router-based** — directs queries to FAQ (RAG pipeline), Troubleshooting Agent, or direct answer
- **LangChain Retrieval** — embedding → vector search (Qdrant/Pinecone) → BGE reranking → LLM generation
- **Troubleshooting Agent** — tool-based (Attendance, Shift, Deduction, Employee Status, Sync Schedule)
- **Answer Generation** — quality grounding check → human handoff if low confidence
- **Memory** — Redis (7-day chat memory, 30-min sessions) + LangChain short-term memory

## Structure

- `core/` — LLM, embeddings, retriever, chains orchestrator, Redis memory/sessions, reranker, domain logic
- `interface/` — FastAPI LINE webhook (`fastapi_app.py`), Gradio test UI (`gradio_app.py`)
- `utils/` — Intent detection, text normalization, language detection, templates, incidents
- `indexers/` — FAQ CSV indexing, data merging, vector DB tools
- `config/` — Tenant config (`tenants.yaml`), incident definitions (`incident_data.yaml`)
- `data/` — FAQ CSVs (public + company-specific), merged outputs

## Code Style

- Python 3.11, type hints encouraged
- Follow existing patterns in `core/` modules (class wrappers: `CustomLLM`, `SentenceTransformerEmbeddings`)
- Async where needed (FastAPI webhook handlers), sync for LLM/embedding calls
- Use `get_redis_client()` singleton for Redis connections
- All text processing must handle both Thai and English

## Commands

```bash
# Install
pip install -r requirements.txt

# Run FastAPI (production — LINE webhook)
python main.py api

# Run Gradio (testing UI)
python main.py gradio

# Index FAQs
python indexers/index_faq_csv.py --file data/faqs/public_faq.csv --company salary_hero

# Merge FAQs
python indexers/merge_data.py

# Debug Qdrant
python indexers/inspect_qdrant.py
```

## Skills (Claude Code slash commands)

| Skill | Use for |
|-------|---------|
| `/index` | Merge + push FAQs to Qdrant (first time or new data) |
| `/index all` | Index all companies × both languages |
| `/qdrant status` | See what collections exist in Qdrant |
| `/qdrant reindex <company> <lang>` | Full refresh of a collection |
| `/qdrant delete <company> <lang>` | Remove a collection |
| `/qdrant add-tenant <name>` | Onboard a new company |
| `/changelog` | Log changes after finishing a task |

## Conventions

- Redis keys: `chat:memory:{tenant}:{user}:{lang}` (memory), `chat:session:{tenant}:{user}` (session)
- Vector collections: `{company_id}_{language}`
- CSV format: `Context | Question | Answer | source_type | company_id | incident | tags | followup_questions`
- Intent types: greeting, thanks, goodbye, frustrated, confused, unclear, question
- Config in YAML (`config/`), never hardcoded
- All queries scoped to tenant namespace
- Always consider Thai + English templates in `utils/templates.py`
- Graceful degradation: if Redis/Qdrant/LLM fails → fallback templates, never crash

## Environment Variables

Required: `ANTHROPIC_API_KEY`, `QDRANT_HOST`, `QDRANT_API_KEY`, `REDIS_URL`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`
Optional: `PINECONE_API_KEY`, `VECTOR_BACKEND` (qdrant|pinecone), `ENABLE_EMBEDDING_CACHE`, `ENABLE_PARALLEL_PROCESSING`

## Token Saving Rules

When the user says "save tokens", "less token", "token saving mode", or similar — follow ALL of these:

- Read only the specific file/lines mentioned. Never explore the repo broadly.
- Do not read files unless directly required for the task.
- Skip `/changelog` unless user explicitly asks for it.
- Prefer `Edit` over `Read` + rewrite. Prefer targeted edits over full rewrites.
- Do not run exploratory bash commands (find, grep across whole repo) unless asked.
- Respond concisely — no summaries, no recaps, no "here's what I did".
- Use `Explore` subagent for any search that needs more than 2 grep/find calls.
- Remind the user to `/compact` after every 2–3 task completions.
- Suggest `/clear` before starting an unrelated new task.
- Suggest switching to `/model claude-haiku-4-5` for simple single-file edits.
