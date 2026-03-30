"""
FAQ CSV indexer.

Reads FAQ CSV files and indexes them into Qdrant (or Pinecone).
Run manually when knowledge base is updated.

Usage:
    python indexers/index_faq_csv.py --file data/faqs/public_faq.csv --company salary_hero
    python indexers/index_faq_csv.py --file data/company/hns/hns_company.csv --company hns
"""

import argparse
import csv
import os
import sys
from pathlib import Path

# TODO Phase 2: import rag modules
# from rag.embeddings import embed_documents
# from rag.query_cleaner import clean_query

CSV_COLUMNS = ["Context", "Question", "Answer", "source_type", "company_id", "incident", "tags", "followup_questions"]


def index_csv(file_path: str, company_id: str, language: str = "th") -> int:
    """
    Index a FAQ CSV file into the vector DB.

    Returns the number of records indexed.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


def _read_csv(file_path: str) -> list[dict]:
    """Read and validate CSV file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {file_path}")

    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index FAQ CSV into vector DB")
    parser.add_argument("--file", required=True, help="Path to CSV file")
    parser.add_argument("--company", required=True, help="Company / tenant ID")
    parser.add_argument("--language", default="th", choices=["th", "en"])
    args = parser.parse_args()

    count = index_csv(args.file, args.company, args.language)
    print(f"Indexed {count} records for {args.company} ({args.language})")
