---
name: solutions
description: Convert Freshdesk Solutions.json → FAQ CSV and index per-company into Qdrant. Full pipeline: download file → /solutions <path> → done.
---

Always run Python with `PYTHONPATH=. python` from the project root.

Parse <args> for sub-command and parameters. If no args given, run the **default full pipeline**.

---

## Default — convert + index all  (no args, or just a file path)

If <args> is empty or looks like a file path (starts with `/` or `~/`):

**Step 1 — Ask for file path** (if not provided in args):
> "Where is the Solutions.json file? (e.g. ~/Downloads/Solutions.json)"

**Step 2 — Convert** Solutions.json → `data/faqs/solutions_faq.csv`:
```bash
PYTHONPATH=. python indexers/convert_solutions_json.py --file <path>
```
Show the summary output (total articles, source types, default vs company-specific counts).

**Step 3 — Index** all companies into Qdrant (each company = company-specific + all defaults merged):
```bash
PYTHONPATH=. python indexers/index_solutions.py
```
Show which collections were created and how many articles each has.

**Step 4 — Verify**:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```
Report collection names and record counts.

At the end summarise: how many companies indexed, total articles, and any errors.

---

## `index` — re-index from existing CSV (skip convert step)

When args = `index` (no company specified):

Run using the already-converted `data/faqs/solutions_faq.csv`:
```bash
PYTHONPATH=. python indexers/index_solutions.py
```

Use this when Solutions.json hasn't changed — skips the conversion step.

---

## `index <company>` — index one company only

When args = `index <company>`:

```bash
PYTHONPATH=. python indexers/index_solutions.py --company <company>
```

Useful after onboarding a new company: indexes that company's articles + all defaults.
Report the collection name and article count.

---

## `status` — show what solutions collections exist

List all Qdrant collections and highlight which ones came from solutions data:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```

Then explain the structure:
- `salary_hero_th` = 52 default articles (fallback for any tenant)
- `{company}_th` = company-specific + defaults merged

---

## Key facts to know

**Why per-company collections?**
Each company gets its own Qdrant collection containing:
- Their company-specific articles (e.g. specific withdrawal conditions for that company)
- All 52 default articles (generic articles that apply to every company)

This means every collection is self-contained — no cross-collection fallback needed.

**Source types in the data:**
- `non_login`           — pre-login issues (registration, phone change, login problems)
- `login`              — post-login features (phone change when already logged in)
- `feature_sod`        — Salary-on-Demand withdrawal features
- `feature_flexben`    — Flexible Benefits
- `feature_direct_debit` — Bank account linking

**Tags:**
- `default`          — generic article, safe for all companies
- `company_specific` — belongs to a specific company only

**Full workflow (every time a new Solutions.json is downloaded):**
```
/solutions ~/Downloads/Solutions.json
```
That's it — convert + index all companies in one command.

---

At the end of any operation, ask: "Run /changelog to log this?"
