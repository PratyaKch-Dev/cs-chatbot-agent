# 019 — Image-Only Clarifying Question Flow

**Date:** 2026-05-10
**Type:** feature
**Phase:** 2

---

## Summary
When a user sends an image with no text, the bot now stores the vision-generated description as pending context, asks a clarifying question with 2–3 keyword-derived suggestions, then on the user's next reply combines the image situation with the question before routing and retrieval — so the final answer is grounded in both the screenshot state and the user's actual intent.

## Added
- `memory/pending_image.py` — Redis save/load/clear for pending image context. Key: `chat:pending_image:{tenant}:{user}`, TTL: 30 min (matches session window)
- `pipeline/image_intent.py` — keyword classifier: matches vision description against `config/image_intents.yaml` and returns `(intent_id, suggestions)`
- `pipeline/image_handler.py` — provider-agnostic helpers: `extract_image_only_description()` detects image-only buffer batches; `build_clarifying_reply()` saves pending + builds the reply text
- `config/image_intents.yaml` — 5 keyword patterns (fee_outstanding, balance_zero, withdrawal_failed, login_issue, error_message) + generic fallback, each with TH/EN suggestions
- `llm/templates.py:build_image_clarify_reply()` — builds clarifying reply showing full image description (not truncated) + bulleted suggestions
- `pipeline/orchestrator.py:_prepend_image_situation()` — prepends image situation to RAG context with a "primary grounding" label so the LLM treats it as authoritative alongside retrieved FAQ docs
- `config/memory.yaml` + `memory/config.py` — added `pending_image` TTL (1800s) and `chat:pending_image` key prefix

## Changed
- `pipeline/orchestrator.py:handle_message()` — at entry, loads pending image from Redis, prepends to message as `[ภาพ] {image}\nคำถาม: {reply}`, clears Redis, and passes `image_situation` string through all pipeline sub-paths
- `pipeline/orchestrator.py:_run_faq()` — augments retrieval query with image keywords; skips the high-confidence direct-pass shortcut when image context is present; calls `_prepend_image_situation()` to inject into context
- `pipeline/orchestrator.py:_run_faq_followup()` — same retrieval augmentation and context injection as `_run_faq`
- `pipeline/router.py:_llm_classify()` — accepts `image_situation` as a separate named input and injects it as "User's screen (from image sent earlier)" section — router LLM sees both image state and user question and decides routing + `search_query` using both
- `pipeline/router.py:decide_route()` — accepts and passes through `image_situation`
- `interface/gradio_app.py:process_messages()` — branches on image-only batch: calls `build_clarifying_reply()` instead of pipeline; shows `[image-flow]` trace in the trace box; clears pending image on session reset
- `interface/freshchat_app.py` — stub updated with exact integration points for image download, `extract_image_only_description`, and `build_clarifying_reply`
- `planning/PRESENTATION.md` — added "Image-Only Clarifying Flow" section with full flow diagram, file table, and edge cases

## Removed
- Nothing removed

## Notes
- Gradio is the current test interface; Freshchat is the real target — all helpers are provider-agnostic
- `[image-flow]` logger fires at four points: DETECTED (image-only batch), SAVED (pending to Redis), COMBINED (pending + user reply), APPLIED (image injected into context) — visible in console and Gradio trace box
- Troubleshooting path (`_run_troubleshooting_new`) does not yet receive `image_situation` — only FAQ paths do
- Edge cases handled: image+text together (pre-combined, no clarifying question), 30-min Redis TTL auto-expiry, second image overwrites pending, Redis-down graceful degradation
