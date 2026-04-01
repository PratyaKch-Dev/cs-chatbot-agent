# 007 — FAQ Answer Quality & Pipeline Logging

**Date:** 2026-04-01
**Type:** feature + fix
**Phase:** 2

---

## Summary
Added structured pipeline logging (readable + JSONL) and fixed multiple LLM answer quality issues. A critical regex bug in `_PREAMBLE_RE` was stripping entire single-line answers, causing 71% coverage — fixing it brought coverage to 97% on 31 test questions.

## Added
- `utils/pipeline_logger.py` — `PipelineTrace` class writes one readable block per request to `logs/faq_trace.log` and one JSON line to `logs/faq_trace.jsonl`; includes grounding bar, retrieval hits, answer preview, and duration
- `scripts/test_faq.py` — batch tester that runs 31 Thai FAQ questions grouped by section and prints a coverage summary table

## Changed
- `pipeline/answer_generator.py`:
  - Tightened Thai system prompt: added rules to forbid preamble phrases ("จากข้อมูล...", "ตามข้อมูล..."), related-questions sections, and answering questions not asked
  - Added `_clean_answer()` with `_PREAMBLE_RE` to strip "from context" boilerplate
  - Added `_RELATED_RE` to strip "เกี่ยวกับคำถามที่เกี่ยวข้อง:" sections the LLM still generates
  - Fixed `_PREAMBLE_RE`: changed `[^,،\n]*` (greedy, no limit) to `[^\n:,،]{0,30}[:\n,،]` (requires separator within 30 chars) — this was stripping entire single-line answers and causing grounding score 0.00
- `rag/retriever.py` — removed `followup_questions` from `build_context()` output; they were being sent to LLM causing it to answer questions not asked
- `interface/gradio_app.py` — wired `PipelineTrace` into `_chat()`, added `logging.basicConfig` for terminal output

## Removed
- Nothing

## Notes
- Coverage: 71% → 97% after preamble regex fix (30/31 questions answered)
- `faq_trace.log` blocks are easy to scan in editor; `faq_trace.jsonl` for scripting
- Grounding threshold stays at 0.25 (word overlap heuristic)