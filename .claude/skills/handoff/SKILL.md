---
name: handoff
description: Save a session summary to .claude/last_compact_summary.md and compact the conversation. Run this before /login to switch accounts.
---

Do these two things in order:

**Step 1** — Write a session summary to `.claude/last_compact_summary.md`. Overwrite any existing content:

```
date: <today's date and time>

## Task
What we were working on this session (1-2 sentences).

## Decisions
Key choices made and why (bullet points, skip if none).

## State
- Done: what's complete
- Pending: what's in progress or not started
- Files changed: list key files touched

## Next step
The single most important thing to do when resuming.
```

**Step 2** — Compact the conversation by summarizing it internally.

After both are done, print:
"Handoff complete. Run /login to switch accounts. When you resume, just say: 'continue from .claude/last_compact_summary.md'"
