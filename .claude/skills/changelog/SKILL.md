---
name: changelog
description: After every change to the project, create the next numbered entry in planning/changes/ and update the CHANGELOG.md index. Always run this after finishing any task.
---

When invoked (with optional $ARGUMENTS as a short title):

1. Read planning/CHANGELOG.md to find the current highest entry number. Next = that number + 1, zero-padded to 3 digits (e.g. 003).

2. Run `git diff --staged` to see exactly what is staged. Use this diff as the source of truth for what was implemented — do not rely on conversation inference.

3. Determine the title:
   - If $ARGUMENTS is provided, use it as the title
   - Otherwise derive the title from the staged diff

4. Create planning/changes/<NNN>_<slug>.md using this structure:

```
# <NNN> — <Title>

**Date:** <today YYYY-MM-DD>
**Type:** scaffold | feature | fix | refactor | config | data
**Phase:** <phase number or pre-phase>

---

## Summary
<1–2 sentences>

## Added
-

## Changed
-

## Removed
-

## Notes
-
```

   Fill in every section from the staged diff. Do not leave placeholders.

5. Add one row to the index table in planning/CHANGELOG.md:
   | [<NNN>](changes/<NNN>_<slug>.md) | <date> | <title> | <type> | <phase> |

6. Ask: "Changelog <NNN> created — commit it?"
   Wait for confirmation before any git commit.
