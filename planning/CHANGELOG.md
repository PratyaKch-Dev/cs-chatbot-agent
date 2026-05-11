# Changelog

Each change is a numbered file in `planning/changes/`.
Add a new file here each time something is updated — never edit old entries.

**To add a new entry:**
1. Create `planning/changes/{next_number}_{short_title}.md`
2. Add a row to the index below

---

## Index

| # | Date | Title | Type | Phase |
|---|------|-------|------|-------|
| [001](changes/001_initial_scaffold.md) | 2026-03-29 | Initial scaffold + PLAN.md | scaffold | pre-phase |
| [002](changes/002_mock_llm_data_adjustments.md) | 2026-03-29 | Mock API, LLM providers, data merge adjustments | refactor + feature | pre-phase |
| [003](changes/003_skills_setup.md) | 2026-03-30 | Skills setup & cleanup | config | pre-phase |
| [004](changes/004_add_gitignore.md) | 2026-03-30 | Add .gitignore | config | pre-phase |
| [005](changes/005_add_docker_compose.md) | 2026-03-30 | Add docker-compose.yml | config | pre-phase |
| [006](changes/006_offline_knowledge_pipeline.md) | 2026-03-31 | Offline knowledge pipeline | feature | 2 |
| [007](changes/007_faq_answer_quality_and_logging.md) | 2026-04-01 | FAQ answer quality & pipeline logging | feature + fix | 2 |
| [008](changes/008_troubleshooting_agent.md) | 2026-04-01 | Troubleshooting Agent (LangChain Tool-Calling) | feature | 2 |
| [009](changes/009_troubleshooting_improvements.md) | 2026-04-02 | Troubleshooting Agent Improvements | fix + feature + data | 2 |
| [010](changes/010_chitchat_and_missing_info_paths.md) | 2026-04-16 | Chitchat & Missing Info Paths + LLM Router | feature + refactor | 2 |
| [011](changes/011_gemini_support_and_perf.md) | 2026-04-16 | Gemini 2.5 Flash support + pipeline performance improvements | feature + refactor | 2 |
| [012](changes/012_multiturn_flow_and_memory_config.md) | 2026-04-20 | Multi-turn Flow & Memory Config | feature + refactor | 2 |
| [013](changes/013_solutions_faq_pipeline_and_template_refinements.md) | 2026-05-03 | Solutions FAQ Pipeline + Answer Template Refinements | feature + data + refactor | 2 |
| [014](changes/014_redis_circuit_breaker_and_multi_message_combiner.md) | 2026-05-03 | Redis Circuit Breaker & Multi-Message Combiner | fix + feature | 2 |
| [015](changes/015_handoff_skill_and_session_resume.md) | 2026-05-03 | Handoff Skill & Session Resume | config | pre-phase |
| [016](changes/016_image_sticker_file_support.md) | 2026-05-03 | Image, Sticker & File Message Support | feature | 2 |
| [017](changes/017_user_profile_api_integration.md) | 2026-05-04 | User Profile API Integration | feature | 3 |
| [018](changes/018_attendance_api_integration.md) | 2026-05-04 | Attendance API Integration | feature | 3 |
| [019](changes/019_image_clarifying_flow.md) | 2026-05-10 | Image-Only Clarifying Question Flow | feature | 2 |
| [020](changes/020_router_v3_smart_retrieval_pinned_faq_user_handoff.md) | 2026-05-11 | Router v3: Smart FAQ Retrieval, Pinned Articles & User-Controlled Handoff | refactor | 3 |
| [021](changes/021_llm_handoff_intent_classification.md) | 2026-05-11 | LLM `handoff_request` Intent Classification | refactor + fix | 3 |