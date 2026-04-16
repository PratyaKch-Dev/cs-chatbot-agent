# 010 — Chitchat & Missing Info Paths + LLM Router

**Date:** 2026-04-16
**Type:** feature + refactor
**Phase:** 2

---

## Summary
Replaced keyword-only routing with a fast LLM (Haiku, max_tokens=10) classifier that returns specific labels mapped to routes and template keys. Added dedicated CHITCHAT and MISSING_INFO pipeline paths served entirely from YAML templates — no RAG, no LLM generation.

## Added
- `config/chitchat_templates.yaml` — Thai + English responses for greeting, thanks, goodbye, frustrated, confused, missing_info
- `pipeline/router.py` — `_llm_classify()` (Haiku router), `_LABEL_TO_ROUTE`, `_INTENT_TO_LABEL`, `_intent_fallback()`, `Route.CHITCHAT`, `Route.MISSING_INFO`, `template_key` field on `RouteDecision`
- `pipeline/answer_generator.py` — chitchat and missing_info branches in `generate_answer()`, `_load_chitchat_templates()`, `get_chitchat_template()`, `template_key` parameter, `llm_failed` escalation gate, off-topic context detection rule in Thai system prompt
- `utils/pipeline_logger.py` — `route_label` field on `PipelineTrace`, updated `set_route()` signature and log line
- `scripts/test_all.py` — full pipeline tester covering all four routes (chitchat, missing_info, FAQ, troubleshooting)
- `tests/unit/test_router.py` — real unit tests replacing TODO stubs (chitchat, missing_info, FAQ, troubleshooting keyword fallback)

## Changed
- `agent/planner.py` — replaced LangChain ReAct agent (`create_tool_calling_agent` / `AgentExecutor`) with deterministic `_TOOL_STRATEGY` dict; added `sub_type` parameter; added `_extract_paycycle_start()` helper
- `llm/intent.py` — implemented `detect_intent()` (was `raise NotImplementedError`); expanded greeting/thanks keyword lists; added UNCLEAR detection for messages < 8 chars
- `interface/gradio_app.py` — added chitchat and missing_info route handlers; fixed `decide_route` call to pass real intent result; passes `sub_type` to `run_troubleshooting_agent`
- `llm/client.py` — added error logging on API failure
- `pipeline/answer_generator.py` — lowered `high_retrieval` threshold from 0.6 → 0.4
- `planning/PRESENTATION.md` — updated architecture diagrams for new router and troubleshooting flow

## Removed
- LangChain `AgentExecutor` / `create_tool_calling_agent` from `agent/planner.py`
- Hardcoded `TEMPLATE_INTENTS` short-circuit and single `TROUBLESHOOTING_KEYWORDS` dict from `pipeline/router.py` (replaced by LLM classifier + `_TOOL_STRATEGY`)

## Notes
- LLM router falls back to intent+keyword matching if API call fails
- Chitchat/missing_info paths have grounding_score=1.0 and was_escalated=False by definition
- Troubleshooting sub-type is now passed through to planner, enabling per-type tool strategies without a ReAct loop
