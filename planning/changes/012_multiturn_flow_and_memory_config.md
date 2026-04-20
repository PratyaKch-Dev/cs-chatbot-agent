# 012 — Multi-turn Flow & Memory Config

**Date:** 2026-04-20
**Type:** feature + refactor
**Phase:** 2

---

## Summary
Introduced full multi-turn conversation flow with active context tracking, upgraded LLM router with conv_state/followup_type, moved all Redis TTL/key config to one YAML file, and made the chat pipeline a single reusable entry point.

## Added
- `config/memory.yaml` — single source of truth for all Redis TTLs, limits, and key prefixes
- `memory/config.py` — loads memory.yaml, exposes typed constants and key-builder functions
- `memory/active_context.py` — tracks active conversation state (FAQ topic or open troubleshooting case); stores `sub_type` so recheck knows which API to call without reverse-mapping
- `pipeline/orchestrator.py` — `handle_message()` single entry point for all interfaces; sub-handlers for troubleshooting recheck, new troubleshooting, faq followup, faq
- `scripts/test_conversation.py` — multi-turn conversation test script

## Changed
- `pipeline/router.py` — outputs structured JSON with `conv_state` (new_query/followup/ambiguous) and `followup_type` (faq_followup/troubleshooting_recheck/null); 3-tier JSON parse fallback for Gemini truncation; PRIORITY RULES in system prompt so greetings always override active context; trimmed to one troubleshooting subtype
- `interface/gradio_app.py` — slimmed to thin wrapper calling `orchestrator.handle_message()`; clear button flushes all Redis state
- `memory/context_cache.py` — switched to `chat:cache` key, freeing `chat:context` for active_context
- `memory/history.py`, `memory/session.py`, `memory/summarizer.py` — hardcoded TTL constants replaced with `memory/config.py` imports
- `llm/client.py` — `record_llm_call` now passes system, history_msgs, prompt, reply for richer trace
- `utils/pipeline_logger.py` — compact trace format with emoji section headers; file writes moved to background thread

## Removed
- `_FOLLOWUP_KEYWORDS` / `_is_followup()` from gradio_app.py — replaced by router conv_state
- `_TOPIC_TO_SUBTYPE` reverse-mapping — replaced by storing `sub_type` directly in active context
- Troubleshooting subtypes attendance/account/deduction from router (only `withdrawal` active for now)

## Notes
- Defensive recheck: if active TS context exists and message is followup/ambiguous, always recheck regardless of router output — guards against Gemini JSON truncation dropping to FAQ
- `format_for_router(ctx)` formats already-loaded active context dict — no second Redis read needed
