---
name: index
description: Guide indexing FAQ CSVs into the vector DB — merge, index, and inspect in the right order.
---

When invoked (with optional <args> like a company name or file path):

1. List available FAQ files to give context:
   - `data/faqs/` — public FAQs
   - `data/company/<company_id>/` — company-specific FAQs

2. Ask the user (if not already provided in <args>):
   - Which company/tenant? (e.g. `salary_hero`, `hns`)
   - Which language? `th` or `en` (default: `th`)
   - Full index or merge-only?

3. Run in this order:

   **Step 1 — Merge** (combine public + company FAQs):
   ```bash
   python indexers/merge_data.py --company <company_id> --language <lang>
   ```
   Output goes to `data/merged/<company_id>_<lang>.csv`

   **Step 2 — Index** (push merged CSV into vector DB):
   ```bash
   python indexers/index_faq_csv.py --file data/merged/<company_id>_<lang>.csv --company <company_id> --language <lang>
   ```

   **Step 3 — Verify** (optional, inspect Qdrant collection):
   ```bash
   python indexers/inspect_qdrant.py
   ```

4. Report how many records were indexed or any errors.

5. Ask: "Run /changelog to log this?"
