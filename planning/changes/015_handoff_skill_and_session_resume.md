# 015 — Handoff Skill & Session Resume

**Date:** 2026-05-03
**Type:** config
**Phase:** pre-phase

---

## Summary
Added a `/handoff` skill that saves a structured session summary and compacts context in one command, enabling smooth account switching. Added auto-resume logic to CLAUDE.md so any new session silently reloads context from the saved summary.

## Added
- `.claude/skills/handoff/SKILL.md` — `/handoff` skill: writes `.claude/last_compact_summary.md` then compacts; run before `/login` to switch accounts

## Changed
- `CLAUDE.md` — added `## Session Resume` section (auto-read handoff file at session start) and `## Token Saving Rules` section

## Removed
- nothing

## Notes
- Handoff file is project-local so both accounts share the same context when opening the same directory
- Token Saving Rules guide Claude to minimize token usage on request
