"""
Data merger.

Merges company-specific FAQs with public FAQs into one file per tenant+language.
Deduplicates by question text (company data takes priority over public data).

Output naming: {company_id}_{language}.csv  →  e.g. hns_th.csv
This matches the Qdrant collection name convention.

Usage:
    python indexers/merge_data.py --company hns --language th
    python indexers/merge_data.py --company hns --language en
"""

import argparse
import csv
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
PUBLIC_FAQ_PATH = DATA_DIR / "faqs" / "public_faq.csv"
MERGED_DIR = DATA_DIR / "merged"

CSV_COLUMNS = [
    "Context", "Question", "Answer",
    "source_type", "company_id", "incident",
    "tags", "followup_questions",
]


def merge_for_company(company_id: str, language: str = "th") -> str:
    """
    Merge public_faq.csv + {company_id}_company.csv → merged/{company_id}_{language}.csv

    Priority: company-specific rows override public rows with the same Question.
    Returns the path to the output file.
    """
    company_csv = DATA_DIR / "company" / company_id / f"{company_id}_company.csv"

    if not PUBLIC_FAQ_PATH.exists():
        raise FileNotFoundError(f"Public FAQ not found: {PUBLIC_FAQ_PATH}")
    if not company_csv.exists():
        raise FileNotFoundError(f"Company FAQ not found: {company_csv}")

    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = MERGED_DIR / f"{company_id}_{language}.csv"

    # Load public FAQ rows
    public_rows = _read_csv(PUBLIC_FAQ_PATH)

    # Load company-specific rows
    company_rows = _read_csv(company_csv)

    # Deduplicate: build dict keyed by Question (company rows win)
    merged: dict[str, dict] = {}
    for row in public_rows:
        merged[row["Question"].strip().lower()] = row
    for row in company_rows:
        merged[row["Question"].strip().lower()] = row  # overrides public if same question

    final_rows = list(merged.values())

    _write_csv(output_path, final_rows)
    return str(output_path)


def _read_csv(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if any(row.values()):   # skip blank lines
                rows.append(dict(row))
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge FAQ CSVs for a company")
    parser.add_argument("--company", required=True, help="Company / tenant ID (e.g. hns)")
    parser.add_argument("--language", default="th", choices=["th", "en"], help="Language")
    args = parser.parse_args()

    output = merge_for_company(args.company, args.language)
    print(f"Merged → {output}")
