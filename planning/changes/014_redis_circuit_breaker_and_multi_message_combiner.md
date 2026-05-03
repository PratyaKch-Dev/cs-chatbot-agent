# 014 — Redis Circuit Breaker & Multi-Message Combiner

**Date:** 2026-05-03
**Type:** fix + feature
**Phase:** 2

---

## Summary
Added a Redis circuit breaker so unavailable-Redis errors surface once at startup instead of per-message. Introduced a two-phase multi-message combiner for the Gradio UI so rapidly-sent messages are combined into one pipeline call, with each user bubble displayed separately and a single bot reply under the last message.

## Added
- `pipeline/combiner.py` — thread-safe push/claim/is_current/complete/reset combiner for Gradio
- `interface/freshchat_app.py` — Freshchat webhook stub (FastAPI router, TODO implementation)
- `test_gradio_combiner.py` — unit tests for combiner logic (single message, fast two-message combine, history preservation)
- `CLAUDE.md` — Token Saving Rules section: behaviors Claude follows when user says "save tokens" / "less token"
- `_committed_store` module-level dict in `gradio_app.py` — avoids Gradio state propagation race conditions between queued process_messages calls

## Changed
- `memory/redis_client.py` — added `_available` circuit breaker; `get_redis_client()` raises immediately when circuit is open; `check_redis_health()` opens/closes circuit and logs once
- `main.py` — calls `check_redis_health()` at warmup so Redis status is known before first user message; added `demo.queue()` for Gradio concurrency support
- `interface/gradio_app.py` — replaced single `respond()` handler with two-phase `enqueue_msg` + `process_messages`; retry loop combines inflight + pending when new messages arrive mid-flight; bot reply shown only under last message in a combined batch (`[[msg, None], ..., [last_msg, reply]]`)
- `interface/fastapi_app.py` — mounts Freshchat router
- `memory/summarizer.py` — downgraded `load failed` / `save failed` logs from WARNING to DEBUG
- `memory/context_cache.py` — downgraded all Redis-error logs from WARNING to DEBUG
- `memory/history.py` — downgraded Redis-error logs from WARNING to DEBUG
- `memory/session.py` — downgraded Redis-error logs from WARNING to DEBUG
- `llm/intent.py` — added `ดีคับ`, `ดีคะ` to Thai greeting keywords

## Removed
- Old single-handler `respond()` and `_chat()` functions from `gradio_app.py`

## Notes
- Circuit breaker pattern: first Redis failure logs WARNING and sets `_available=False`; subsequent calls raise immediately without attempting connection; recovers if `check_redis_health()` is called and Redis comes back
- Combiner race fix: `_committed_store` is updated synchronously after each completion; queued process_messages calls read from it instead of potentially stale Gradio gr.State
