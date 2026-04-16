# 011 — Gemini 2.5 Flash support + pipeline performance improvements

**Date:** 2026-04-16
**Type:** feature + refactor
**Phase:** 2

---

## Summary
Implemented the Google Gemini provider (previously a stub), wired per-step latency tracking into the pipeline trace, and fixed two performance issues that caused the first request to take ~14s.

## Added
- `llm/providers/google.py` — full `GoogleProvider` implementation using `google-generativeai` SDK with `gemini-2.5-flash` as default model, retry logic, and `system_instruction` support
- `main.py` — `_warmup_models()` pre-loads embedding and reranker models at startup for both `api` and `gradio` modes
- `utils/pipeline_logger.py` — active-trace registry (`set_active_trace`, `record_llm_call`) so `call_llm` can push LLM call metadata without changing pipeline signatures
- `utils/pipeline_logger.py` — `PipelineTrace.mark_step()` for recording non-LLM step timings (e.g. retrieval)
- `utils/pipeline_logger.py` — `PipelineTrace.step_times` and `llm_calls` fields; TIMINGS block in readable log output showing per-step latency, model name, token counts, and TOTAL
- `interface/gradio_app.py` — retrieval step timing via `trace.mark_step("retrieval", ...)`

## Changed
- `llm/client.py` — added `step` param; measures per-call latency and pushes to active trace via `record_llm_call`
- `pipeline/router.py` — passes `step="router"` to `call_llm` for correct trace labelling
- `rag/retriever.py` — reduced `VECTOR_SEARCH_TOP_K` from 10 → 5 (halves reranker inference time with negligible quality impact at top-3 return)
- `requirements.txt` — updated Google Gemini comment; `google-generativeai` kept at 0.7.2 for `langchain-google-genai` compatibility
- `utils/pipeline_logger.py` — `PipelineTrace.__post_init__` registers trace as active; `flush()` clears it; `_write_jsonl` includes `step_times` and `llm_calls`

## Removed
- `llm/providers/google.py` — removed `NotImplementedError` stubs

## Notes
- Switch to Gemini via `.env`: `LLM_PROVIDER=google`, `GOOGLE_API_KEY=...`, `LLM_MODEL=gemini-2.5-flash`
- Warmup moves ~6-8s cold-start cost to server startup; subsequent requests target ~2.5s
- Local embedding model (`distiluse`) is preferred over Google Embeddings API for persistent processes — 5ms vs 150-200ms per request after warmup
