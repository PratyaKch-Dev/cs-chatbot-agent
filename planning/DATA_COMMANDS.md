# Data Commands Reference

Quick reference for all data pipeline commands.
Run all commands from the project root directory.

---

## 1. Merge FAQs

Combines `public_faq.csv` + `{company}_company.csv` into `data/merged/{company}_{lang}.csv`.
Company-specific rows override public rows on duplicate questions.

```bash
# HNS — Thai
python indexers/merge_data.py --company hns --language th

# HNS — English (when EN data is ready)
python indexers/merge_data.py --company hns --language en

# Adding a new company
python indexers/merge_data.py --company {company_id} --language th
```

**Input files:**
```
data/faqs/public_faq.csv                     ← shared across all companies
data/company/{company_id}/{company_id}_company.csv  ← company-specific
```

**Output:**
```
data/merged/{company_id}_{language}.csv       ← ready for indexing
```

**When to run:** Every time `public_faq.csv` or a company CSV is updated.

---

## 2. Index FAQs into Vector DB

Embeds and uploads merged CSV rows into Qdrant.
Collection name: `{company_id}_{language}` (matches `tenants.yaml`).

```bash
# Index merged HNS Thai FAQ
python indexers/index_faq_csv.py \
  --file data/merged/hns_th.csv \
  --company hns \
  --language th

# Index raw company CSV directly (skips merge)
python indexers/index_faq_csv.py \
  --file data/company/hns/hns_company.csv \
  --company hns \
  --language th

# Index public FAQ only
python indexers/index_faq_csv.py \
  --file data/faqs/public_faq.csv \
  --company salary_hero \
  --language th
```

> **Note:** Requires `QDRANT_HOST` and `QDRANT_API_KEY` in `.env`. Implemented in Phase 2.

---

## 3. Full Refresh (Merge + Index)

Run both steps together when rebuilding a company's knowledge base from scratch.

```bash
# HNS Thai — full refresh
python indexers/merge_data.py --company hns --language th && \
python indexers/index_faq_csv.py \
  --file data/merged/hns_th.csv \
  --company hns \
  --language th
```

---

## 4. Inspect Vector DB

Debug what's stored in Qdrant.

```bash
# List all collections and record counts
python indexers/inspect_qdrant.py

# Inspect a specific collection (show 5 sample records)
python indexers/inspect_qdrant.py --collection hns_th

# Show more records
python indexers/inspect_qdrant.py --collection hns_th --limit 20
```

> **Note:** Implemented in Phase 2.

---

## 5. CSV Format Reference

All FAQ CSV files must follow this column structure:

| Column | Required | Description | Example |
|--------|----------|-------------|---------|
| `Context` | ✅ | Topic / category | `การถอนเงิน` |
| `Question` | ✅ | The FAQ question | `ถอนเงินได้กี่ครั้งต่อวัน` |
| `Answer` | ✅ | The answer | `สูงสุด 1 ครั้งต่อวัน` |
| `source_type` | ✅ | `faq` \| `incident` \| `company` | `faq` |
| `company_id` | ✅ | Tenant identifier | `hns` |
| `incident` | ❌ | Incident ID if related | `INC-001` |
| `tags` | ❌ | Semicolon-separated tags | `withdrawal;limit` |
| `followup_questions` | ❌ | Suggested follow-ups | `วงเงินถอนสูงสุดคือเท่าไหร่?` |

**Example row:**
```csv
การถอนเงิน,ถอนเงินได้กี่ครั้งต่อวัน,สูงสุด 1 ครั้งต่อวัน,faq,hns,,withdrawal;limit,วงเงินถอนสูงสุดคือเท่าไหร่?
```

---

## 6. Adding a New Company

Step-by-step to onboard a new tenant:

```bash
# 1. Create company CSV
mkdir -p data/company/{company_id}
touch data/company/{company_id}/{company_id}_company.csv
# → add FAQ rows following the CSV format above

# 2. Add tenant config
#    edit config/tenants.yaml — copy the hns block and update fields

# 3. Merge
python indexers/merge_data.py --company {company_id} --language th

# 4. Index
python indexers/index_faq_csv.py \
  --file data/merged/{company_id}_th.csv \
  --company {company_id} \
  --language th

# 5. Verify
python indexers/inspect_qdrant.py --collection {company_id}_th
```

---

## 7. Mock Users Reference

Mock employee data is stored in `agent/clients/mock/users.json`.
Use these `employee_id` values when testing the troubleshooting agent:

| employee_id | Scenario | Expected agent behavior |
|-------------|----------|------------------------|
| `EMP001` | Normal active user | Should confirm eligibility, show attendance/deductions |
| `EMP002` | Suspended account | Should detect `status=suspended`, explain account blocked |
| `EMP003` | Not enrolled | Should detect `enrolled=false`, guide to HR enrollment |
| `EMP004` | Sync pending | Should detect `sync_status=pending`, explain limit not updated |
| `EMP005` | Blacklisted | Should detect `blacklisted=true`, advise contact HR |

To add a new mock user, append a new entry to `agent/clients/mock/users.json`
following the existing structure.
