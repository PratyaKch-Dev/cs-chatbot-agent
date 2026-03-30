# 002 — Mock API, LLM Providers, Data Merge Adjustments

**Date:** 2026-03-29
**Type:** refactor + feature
**Phase:** pre-phase (adjustments before Phase 1)

---

## Summary

Three areas adjusted before starting Phase 1 implementation:
1. Mock clients now load from a single JSON file instead of hardcoded data
2. Real clients use token-based auth instead of employee_id
3. LLM is now provider-agnostic (Claude / GPT / Gemini swappable via env var)
4. Data merge pipeline fully implemented and `hns_th.csv` generated

---

## Added

- `agent/clients/mock/users.json` — single source of mock data, 5 users covering distinct scenarios:
  - `EMP001` — Normal active user, all systems good
  - `EMP002` — Suspended / blocked account
  - `EMP003` — Not enrolled in Salary Hero
  - `EMP004` — Sync pending, withdrawal limit not updated
  - `EMP005` — Blacklisted user
- `agent/clients/mock/data_loader.py` — loads `users.json` once (module-level cache), exposes `get_user(employee_id)`
- `llm/providers/` package:
  - `base.py` — `BaseLLMProvider` ABC: `chat()`, `get_langchain_llm()`, `get_model_name()`, `get_fallback_response()`
  - `anthropic.py` — Claude provider (Phase 1 implementation target)
  - `openai.py` — GPT-4o-mini provider stub (Phase 8)
  - `google.py` — Gemini 1.5 Flash provider stub (Phase 8)
- `data/merged/hns_th.csv` — generated: 9 public + 4 HNS rows = 13 rows total

## Changed

- **All 5 mock clients** — replaced hardcoded data with `data_loader.get_user(employee_id)` lookup
- **All 5 real clients** — constructor now takes `token: str`; sets `Authorization: Bearer {token}` header; `employee_id` kept in method args for interface consistency, ignored by backend (backend resolves user from token)
- `agent/clients/base.py` — added docstring clarifying mock vs real auth model
- `llm/client.py` — rewritten as factory: `get_provider()` reads `LLM_PROVIDER` env var (`anthropic|openai|google`), returns singleton; `call_llm()` and `get_llm()` delegate to provider
- `indexers/merge_data.py` — fully implemented: reads both CSVs, deduplicates by question (company rows win), writes `data/merged/{company_id}_{language}.csv`
- `requirements.txt` — added `openai`, `langchain-openai`, `google-generativeai`, `langchain-google-genai`; removed duplicate `langchain-anthropic` (moved under LLM section)
- `.env.example` — added `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`

## Notes

- Switching LLM provider requires only one env var change: `LLM_PROVIDER=openai`
- To add a new provider: create `llm/providers/{name}.py` extending `BaseLLMProvider`, add a case in `llm/client.py`
- To add a mock user: append a new entry to `agent/clients/mock/users.json` following existing structure
