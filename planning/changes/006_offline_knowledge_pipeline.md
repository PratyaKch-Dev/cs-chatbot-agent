# 006 — Offline Knowledge Pipeline

**Date:** 2026-03-31
**Type:** feature
**Phase:** 2

---

## Summary
Implemented the full offline knowledge indexing pipeline: embeddings, query cleaning, Qdrant indexer, and inspector. Added unit tests and Qdrant management skills.

## Added
- `rag/embeddings.py` — `get_model()` lazy-load singleton, `embed_documents()` batch encoding, `get_embedding_cached()` LRU cache
- `rag/query_cleaner.py` — `clean_query()` normalization (lowercase, whitespace, punctuation, Thai/EN synonyms)
- `indexers/index_faq_csv.py` — `index_csv()` reads merged CSV, embeds, upserts into Qdrant collection
- `indexers/inspect_qdrant.py` — `list_collections()` and `inspect_collection()` debug utilities
- `tests/unit/test_query_cleaner.py` — 15 unit tests for normalization logic
- `tests/unit/test_embeddings.py` — 4 unit tests with mocked model (shape, cache hit)
- `.claude/skills/qdrant/SKILL.md` — `/qdrant` skill for status, reindex, delete, inspect, add-tenant
- `CLAUDE.md` — Skills reference table added

## Changed
- `.claude/skills/index/SKILL.md` — expanded with all sub-commands and `PYTHONPATH=.` convention
- `rag/query_cleaner.py` — fixed stripping regex to preserve Thai combining characters (e.g. `้`)

## Notes
- All commands require `PYTHONPATH=.` prefix to resolve `rag` module
- `.env` must be loaded via `python-dotenv` — Qdrant host not picked up otherwise
- Embedding model uses Apple MPS (Metal) on M-series Mac automatically
- 19/19 unit tests passing
