# 020 — Router v3: Smart FAQ Retrieval, Pinned Articles & User-Controlled Handoff

**Date:** 2026-05-11
**Type:** refactor
**Phase:** 3

---

## Summary
Restructured FAQ retrieval into a multi-stage smart pipeline (vector + BGE + LLM rerank + full-scan), pinned the four non-withdrawal troubleshooting subtypes to canonical FAQ articles for deterministic answers + images, and replaced auto-handoff with a user-controlled "transfer" option that appears after N unresolved rechecks. Full design + 13 problems-and-fixes documented in `planning/ROUTER_PLAN.md` v3 section.

## Added
- `pipeline/context_resolver.py` — v2 deterministic resolver emitting only END_FLOW / TRIGGER_HANDOFF / NEW. Length-based pure-signal heuristic (`_is_pure_signal`, ≤ 20 chars) replaces brittle keyword lists. New `_is_handoff_request()` detects explicit user requests for an agent (`ต้องการโอน`, `ติดต่อเจ้าหน้าที่`, `คุยกับคน`, `talk to agent`).
- `pipeline/setfit_router.py` — kept as graceful no-op when model files are missing. Falls back to LLM router; restoring SetFit later only needs `scripts/train_setfit.py` to be re-run.
- `pipeline/orchestrator.py` constants:
  - `_TROUBLESHOOTING_FAQ_TITLES` — label → exact FAQ Question map for the pinned shortcut.
  - `_LLM_RERANK_GRAY_LOW = 0.55`, `_LLM_RERANK_GRAY_HIGH = 0.70`, `_FULL_SCAN_TRIGGER_SCORE = 0.55`.
  - `MAX_TROUBLESHOOTING_RETRIES = 3` — threshold for showing the transfer option (no longer used for auto-escalation).
  - `_CATALOG_TTL_SECONDS = 300` — Qdrant scroll cache for full-scan + pin lookups.
- `pipeline/orchestrator.py` helpers:
  - `_is_fallback_answer()` — detects "ขออภัย ไม่มีข้อมูล…" so we never attach images or persist context on a fallback.
  - `_answer_uses_doc()` — character 5-gram overlap gate that prevents wrong-image attachment when the LLM writes a novel answer.
  - `_load_catalog()` + `_find_article_by_title()` — cached tenant catalog with exact-title lookup for the pinned-FAQ shortcut.
  - `_payload_to_doc()` — converts a raw Qdrant payload into a `RetrievedDocument`.
  - `_bge_full_scan()` — BGE rerank top-5 + LLM picker over the full tenant catalog (~300-500ms cached, last-resort retrieval).
  - `_llm_select_article()` — LLM smart reranker using a cached fast-picker provider (Flash-Lite / Haiku).
  - `_get_fast_picker()` — singleton provider for the picker step; override via `FAST_PICKER_MODEL` env var.
  - `_lazy_rewrite_query()` — LLM query rewrite for very low first-pass scores.
- `pipeline/handoff.py`:
  - `_SUB_TYPE_TOPIC_TH / _EN` — deterministic sub_type → human-readable problem label.
  - `_topic_label()` — resolves the "ปัญหา:" line for the handoff summary.
  - `_fallback_summary()` rewritten to be deterministic (no LLM dependency) using the topic map + active_context fields. LLM path still tried first with `max_tokens=1024` + output validation; falls back on truncation.
- `llm/templates.py`:
  - `_CONFIRMATION_TH_WITH_TRANSFER` / `_CONFIRMATION_EN_WITH_TRANSFER` — extended confirmation with the third "transfer to agent" option.
  - `append_confirmation(..., with_transfer)` — extended API and made idempotent (refuses to append if the marker is already present, prevents duplicate prompts).
- `config/troubleshooting_flows.yaml` — staged-flow configuration scaffold (faq_first → api_check → confirmation).
- `data/router/{build_router_dataset.py, router_train.csv, router_train_auto.csv}` — SetFit training data and builder (kept for future retraining; not loaded at runtime).
- `scripts/{test_scenario_8turn.py, train_setfit.py}` — scenario test harness and SetFit training script.
- `data/faqs/solutions_faq.csv` — withdrawal-how-to synonym rows (`วิธีการเบิกเงิน`, `วิธีเบิกเงิน`, `ขั้นตอนการเบิกเงิน`, `เบิกเงินยังไง`) and new text + image URLs for `ไม่ได้รับเงินที่เบิก` and `ไม่ได้รับรหัส OTP` rows.
- `planning/ROUTER_PLAN.md` — full v3 doc (architecture + 13 problems-and-fixes + files-changed list).
- `planning/PRESENTATION.md` — v3 section appended (current router labels, pinned shortcut, smart retrieval pipeline, recheck loop, resolver heuristics, new active-context fields).

## Changed
- `pipeline/router.py`:
  - `_LABEL_TO_ROUTE`: `troubleshooting_signup / cant_find_company / money_not_arrived / cant_receive_otp` now route to `Route.FAQ` (only `troubleshooting_withdrawal` keeps `Route.TROUBLESHOOTING`). Labels are preserved as `template_key` for analytics.
  - `_LLM_FALLBACK_SYSTEM` updated: new `is_new` field in JSON output, history-prioritized rules, 4-turn history at 120 chars, `troubleshooting_cant_receive_otp` added.
  - `_llm_classify` max_tokens 512 → 1024 (Gemini Flash thinking was eating the budget, truncating JSON to 7 chars).
  - `RouteDecision` exposes `is_new: bool` field.
  - `decide_route()` priority cleaned up (SetFit → LLM → keyword fallback).
- `pipeline/orchestrator.py`:
  - Pin shortcut moved upstream of the `is_new` branching — fires on followups too, regardless of stale `cached_faq` or active context.
  - `TRIGGER_HANDOFF` block: explicit `user_requested_handoff` reason fires immediate handoff; otherwise enters recheck loop (no auto-escalation). After MAX retries, the confirmation prompt switches to the `with_transfer=True` variant.
  - Followup-troubleshooting branch: increments `retry_count` on every turn (was previously stuck at 0 due to topic-shift wipes); belt-and-suspenders re-patch after `_run_troubleshooting_recheck`.
  - Topic-shift code: when LLM says `is_new=True` but the active sub_type matches `decision.template_key`, force `is_new=False` to keep retry_count alive across rechecks.
  - FAQ pipeline: lazy-rewrite (score < 0.35) → LLM smart rerank (0.55–0.70 or close-call) → BGE full-scan (< 0.55) → BGE-trust safety net when picker returns -1 with BGE top ≥ 0.45.
  - Image attach in `_run_faq` and `_run_faq_followup` now gated by `_answer_uses_doc()` (≥ 30% 5-gram overlap) and `not _is_fallback_answer()`.
  - Post-processing for TROUBLESHOOTING route always appends confirmation + sets `status=awaiting_confirmation`, with `with_transfer` flag based on `retry_count`.
- `memory/active_context.py`:
  - `save_troubleshooting_context()` now preserves `retry_count` and `handoff_reason` when the same `sub_type` continues. Previously every recheck call overwrote the full dict, resetting the counter to 0.
- `pipeline/handoff.py`:
  - `_build_handoff_prompt()` injects `problem_label_use_for_ปัญหา_bullet` so the LLM has no opportunity to invent the problem name; also passes `sub_type`, `remark`, and richer context.
  - `_llm_handoff_summary()` max_tokens 300 → 1024; validates output and falls back to deterministic on truncation.
- `llm/templates.py`:
  - `_CONFIRMATION_TH/EN` rewritten to the formal "รบกวนแจ้งผลให้ทราบด้วยค่ะ" wording (was "ตอบโจทย์ไหมคะ? 😊").
- `rag/retriever.py`:
  - `_get_collection_name()` now resolves via `tenants.yaml` `vector_collections`, with fallback to `{tenant_id}_{language}` for backwards compat. Plus English-collection fallback to Thai when the language-specific collection doesn't exist.
- `indexers/index_solutions.py`:
  - Wipe-and-rebuild: `delete_collection()` before `create_collection()` on every run, so stale rows from previous indexings can't poison BGE/LLM rerank.
  - `_load_excluded_source_types()` reads `tenants.yaml` `excluded_source_types` per company; per-company defaults are filtered before indexing.
  - `sys.path` bootstrap so the script works when run from anywhere.
- `config/tenants.yaml`:
  - `hns.company_id`: `"hns"` → `"happy_nest_space"` (must match CSV company_id).
  - `hns.vector_collections.th`: `"hns_th"` → `"happy_nest_space_th"`.
  - `hns.excluded_source_types: [feature_flexben]` added.
- `agent/planner.py`:
  - `_TOOL_STRATEGY` simplified: only `troubleshooting_withdrawal` has active tools; the other four entries are present as empty-list placeholders for future "FAQ-first → API" hybrids.
- `llm/providers/{google,openai,anthropic,base}.py` + `llm/client.py`:
  - Minor signature/typing nits; Gemini thinking-budget comment.
- `memory/summarizer.py`:
  - max_tokens 300 → 1024 (Gemini Flash thinking truncation).
- `utils/pipeline_logger.py`:
  - New fields on `PipelineTrace`: `is_new`, `resolver_action`, `resolver_reason`. `set_resolver()` method. ROUTE line includes `[new]/[followup]` tag + `label=`. System prompts collapsed to 5 lines + "N more lines" indicator. Summary wrapped at 90 chars.

## Removed
- Auto-handoff in troubleshooting flows. The bot no longer escalates on its own — only when the user clicks/types one of the handoff-request phrases.
- `model/setfit_router/` directory (470 MB encoder + tokenizer). The classifier `head.pkl` + training script are retained; if the encoder isn't loaded at runtime, `setfit_router.predict()` returns `None` and the router falls back to the LLM-only path with no behavioural change.
- `_HANDOFF_SYSTEM_*` legacy prompts replaced by enriched versions that reference `problem_label_use_for_ปัญหา_bullet`.
- `_QUESTION_MARKERS` keyword approach in the resolver (proposed but rejected as not scalable). Replaced by `_is_pure_signal()` length check.
- Per-example synonym tuning in the LLM picker prompt (rejected as not scalable). Replaced by generic "match by intent and meaning, not surface vocabulary" guidance + 400-char answer previews.

## Notes
- **Reindex required:** `python indexers/index_solutions.py --company happy_nest_space` to push the new CSV rows + apply the flexben exclusion + wipe stale duplicates.
- **`MAX_TROUBLESHOOTING_RETRIES = 3`** is the threshold for revealing the transfer option, NOT for auto-escalation. To change: edit the constant in `pipeline/orchestrator.py`.
- **Two confirmation prompt variants:**
  - retry < MAX → 2 options (resolved / still issue)
  - retry ≥ MAX → 3 options (resolved / still issue / transfer to agent)
- **Fast picker model** is configurable via `FAST_PICKER_MODEL` env var. Defaults to `gemini-2.5-flash-lite` for Google or `claude-haiku-4-5-20251001` for Anthropic. Picker step is gated through `_get_fast_picker()` cached singleton.
- **Catalog cache TTL** = 5 min (`_CATALOG_TTL_SECONDS = 300`). After reindex, allow up to 5 minutes for pinned answers to refresh, or restart the app to flush the cache.
- **Handoff summary** is now deterministic by default; LLM enrichment is attempted but validated and discarded on truncation. Edit `_SUB_TYPE_TOPIC_TH/EN` in `pipeline/handoff.py` to change the "ปัญหา:" label per subtype.
- **Tenant collection mapping** is now read from `tenants.yaml` `vector_collections` per language. The retriever still falls back to `{tenant_id}_{language}` when no mapping is configured.
