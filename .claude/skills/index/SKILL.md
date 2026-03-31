---
name: index
description: Guide indexing FAQ CSVs into the vector DB — merge, index, and inspect in the right order.
---

When invoked (with optional <args> like a company name, language, or sub-command):

Always run commands with `PYTHONPATH=. python` from the project root.

---

## Sub-commands

### Default — merge + index

If no sub-command given, ask the user (if not already provided in <args>):
- Which company/tenant? (e.g. `hns`, `salary_hero`)
- Which language? `th` or `en` (default: `th`)
- Both languages or one?

Then run in order:

**Step 1 — Merge** (combine public + company FAQs):
```bash
PYTHONPATH=. python indexers/merge_data.py --company <company_id> --language <lang>
```
Output: `data/merged/<company_id>_<lang>.csv`

**Step 2 — Index** (push merged CSV into Qdrant):
```bash
PYTHONPATH=. python indexers/index_faq_csv.py --file data/merged/<company_id>_<lang>.csv --company <company_id> --language <lang>
```

**Step 3 — Verify**:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```

Report how many records were indexed or any errors.

---

### `all` — index all companies + both languages

List all folders under `data/company/` and run merge + index for each company × language (`th`, `en`).

---

### `/qdrant status`

Show Qdrant connection status and list all collections with record counts:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```

---

### `/qdrant reindex <company> <lang>`

Full refresh — delete existing collection, re-merge, re-index:
1. Warn user: "This will delete and rebuild collection `<company>_<lang>`. Continue?"
2. On confirm, run merge then index (index_faq_csv.py will recreate the collection).

---

### `/qdrant delete <company> <lang>`

Delete a specific Qdrant collection:
1. Warn user: "This will permanently delete collection `<company>_<lang>`. Continue?"
2. On confirm, run:
```python
from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv
load_dotenv()
client = QdrantClient(url=os.getenv("QDRANT_HOST"), api_key=os.getenv("QDRANT_API_KEY"))
client.delete_collection("<company>_<lang>")
```

---

### `/qdrant inspect <company> <lang>`

Show sample records from a collection:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```

---

At the end of any operation, ask: "Run /changelog to log this?"
