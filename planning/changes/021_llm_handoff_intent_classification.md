# 021 — LLM `handoff_request` Intent Classification

**Date:** 2026-05-11
**Type:** refactor + fix
**Phase:** 3

---

## Summary
Added an LLM-classified `handoff_request` intent so the bot recognizes "I want to talk to a human" in any wording — no keyword list to maintain. Two-layer protection: resolver keyword fast-path for instant button-click handling, LLM router classification for every paraphrase the keyword list doesn't cover. Anti-example in the prompt prevents legitimate "how do I transfer money" questions from misfiring.

## Added
- `pipeline/router.py`:
  - New label `handoff_request` in `_LABEL_TO_ROUTE` (routes to `Route.TROUBLESHOOTING`; orchestrator catches the `template_key` and escalates immediately).
  - `_LLM_FALLBACK_SYSTEM` prompt extended with `handoff_request` rules: catches any wording semantically equivalent to "transfer me to a human", explicitly excludes "how do I transfer money?" questions which remain `faq`.
- `pipeline/orchestrator.py`:
  - Upstream catch right after the router call — when `decision.template_key == "handoff_request"`, calls `run_handoff_summary` immediately, persists the turn, flushes the trace, returns `was_escalated=True`. Runs before the topic-shift / pin / path-execution blocks so it can't be overridden.

## Changed
- `pipeline/context_resolver.py` `_HANDOFF_REQUEST_WORDS`:
  - Added: `ขอโอน`, `โอนเลย`, `โอนให้เจ้าหน้าที่`, `โอนเจ้าหน้าที่`, `คุยกับแอดมิน`, `ขอแอดมิน`.
  - Removed: `transfer me` was kept but the surrounding "speak with" stays narrower.
- `pipeline/context_resolver.py` `_is_handoff_request()`:
  - Added length-bounded short-form: messages ≤ 15 chars containing `โอน` or `transfer` are treated as handoff requests. Catches single-word replies after the transfer-option button is shown ("โอน") without false-matching long questions like "เบิกแล้วเงินโอนไปบัญชีไหน".

## Removed
- Reliance on keyword-only detection for handoff. The resolver fast-path remains as an optimization, but the LLM router is now the source of truth for semantic intent.

## Notes
- **Bug this fixes:** user typed `โอน` or `โอนให้เจ้าหน้าที่` (no `ไป`) and the bot kept showing the recheck answer because neither matched `_HANDOFF_REQUEST_WORDS` exactly.
- **Verified paraphrases now classified as `handoff_request`:**
  - `โอน`, `โอนเลย`, `โอนให้เจ้าหน้าที่`
  - `ต้องการคุยกับคนจริงๆ`, `ขอเจ้าหน้าที่ช่วยที`, `แอดมินช่วยหน่อย`
  - `i want a human`, `transfer me to agent`
- **Verified false-positive guards held:**
  - `โอนเงินไปบัญชีไหน` → `faq` (legitimate question about money transfer)
  - `ทำไมเบิกเงินไม่ได้` → `troubleshooting_withdrawal`
- No additional cost — the router LLM call runs on every message anyway; adding one label to its prompt is free.
- Future paraphrases (`ขอใครก็ได้มาช่วยที`, novel wordings) will be caught by the LLM without needing code changes — closes the loop on the "keyword lists don't scale" feedback that came up multiple times.
