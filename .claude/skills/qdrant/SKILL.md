---
name: qdrant
description: Manage Qdrant collections — status, reindex, delete, inspect.
---

Shortcut into the Qdrant management commands. Always run Python with `PYTHONPATH=.` from project root. Always load `.env` before connecting.

Parse <args> for the sub-command and parameters:

---

## `status` (default if no args)

List all Qdrant collections and their record counts. Run:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```

---

## `reindex <company> <lang>`

Full refresh of a collection:
1. Warn: "This will delete and rebuild `<company>_<lang>`. Continue?"
2. On confirm:
```bash
PYTHONPATH=. python indexers/merge_data.py --company <company> --language <lang>
PYTHONPATH=. python indexers/index_faq_csv.py --file data/merged/<company>_<lang>.csv --company <company> --language <lang>
```

---

## `delete <company> <lang>`

Delete a collection permanently:
1. Warn: "This will delete collection `<company>_<lang>`. Continue?"
2. On confirm, run this Python snippet:
```python
from dotenv import load_dotenv; load_dotenv()
import os
from qdrant_client import QdrantClient
client = QdrantClient(url=os.getenv("QDRANT_HOST"), api_key=os.getenv("QDRANT_API_KEY"), prefer_grpc=False)
client.delete_collection("<company>_<lang>")
print("Deleted.")
```

---

## `inspect <company> <lang>`

Show sample records from a collection:
```bash
PYTHONPATH=. python indexers/inspect_qdrant.py
```

---

## `add-tenant <company>`

Guide adding a new tenant:
1. Check if `data/company/<company>/` exists — if not, create it and explain CSV format
2. Check if `config/tenants.yaml` has an entry — if not, show the template to add
3. Run index for both `th` and `en`

---

At the end, ask: "Run /changelog to log this?"
