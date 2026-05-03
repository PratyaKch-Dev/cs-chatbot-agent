"""
Index solutions_faq.csv into Qdrant — one collection per company.

Each company collection contains:
  • company-specific articles  (company_id = that company)
  • ALL default articles        (company_id = 'salary_hero' or 'no_ta', tags includes 'default')

This means every collection is self-contained — no cross-collection fallback needed.

Usage:
    # Index all companies found in the CSV
    python indexers/index_solutions.py

    # Index one specific company only
    python indexers/index_solutions.py --company rd

    # Use a different source file
    python indexers/index_solutions.py --file data/faqs/solutions_faq.csv

Collections created:  {company_id}_th   (e.g. rd_th, boonthavorn_th, salary_hero_th)
"""

import argparse
import csv
import logging
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from rag.embeddings import EMBEDDING_DIM, embed_documents
from rag.query_cleaner import clean_query

logging.basicConfig(level=logging.INFO, format="%(message)s")
_logger = logging.getLogger("index_solutions")

DEFAULT_CSV  = "data/faqs/solutions_faq.csv"
LANGUAGE     = "th"
_DEFAULT_TAG = "default"


def _get_qdrant() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_HOST", "localhost"),
        api_key=os.getenv("QDRANT_API_KEY"),
        prefer_grpc=False,
    )


def _read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _is_default(row: dict) -> bool:
    return _DEFAULT_TAG in [t.strip() for t in row.get("tags", "").split(";")]


def _index_rows(client: QdrantClient, rows: list[dict], company_id: str) -> int:
    """Embed and upsert rows into {company_id}_th collection."""
    if not rows:
        return 0

    collection = f"{company_id}_{LANGUAGE}"

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        _logger.info(f"  created collection {collection}")

    texts = [
        clean_query(
            f"{r.get('Context', '')} {r.get('Question', '')}",
            LANGUAGE,
        )
        for r in rows
    ]
    vectors = embed_documents(texts)

    points = [
        PointStruct(
            id=i,
            vector=vec,
            payload={
                "context":            r.get("Context", ""),
                "question":           r.get("Question", ""),
                "answer":             r.get("Answer", ""),
                "source_type":        r.get("source_type", ""),
                "company_id":         r.get("company_id", company_id),
                "incident":           r.get("incident", ""),
                "tags":               r.get("tags", ""),
                "followup_questions": r.get("followup_questions", ""),
                "image_urls":         r.get("image_urls", ""),
            },
        )
        for i, (r, vec) in enumerate(zip(rows, vectors))
    ]

    client.upsert(collection_name=collection, points=points)
    return len(points)


def index_all(csv_path: str, only_company: str = "") -> None:
    all_rows = _read_csv(csv_path)

    # Separate defaults from company-specific rows
    default_rows  = [r for r in all_rows if _is_default(r)]
    specific_rows = [r for r in all_rows if not _is_default(r)]

    # Group company-specific by company_id
    by_company: dict[str, list[dict]] = defaultdict(list)
    for r in specific_rows:
        cid = r.get("company_id", "").strip()
        if cid:
            by_company[cid].append(r)

    client = _get_qdrant()

    # 1. salary_hero_th  — defaults only (fallback for any tenant with no specific data)
    if not only_company or only_company == "salary_hero":
        n = _index_rows(client, default_rows, "salary_hero")
        _logger.info(f"  salary_hero_th  ← {n} default articles")

    # 2. Per-company collections — company-specific + all defaults
    for company_id, rows in sorted(by_company.items()):
        if only_company and company_id != only_company:
            continue
        merged = rows + default_rows   # company-specific first, defaults appended
        n = _index_rows(client, merged, company_id)
        _logger.info(
            f"  {company_id}_th  ← {len(rows)} specific + {len(default_rows)} defaults = {n} total"
        )

    if only_company and only_company not in by_company and only_company != "salary_hero":
        # Company not in solutions data — index defaults only for this tenant
        _logger.warning(
            f"  '{only_company}' has no specific articles; indexing defaults only"
        )
        n = _index_rows(client, default_rows, only_company)
        _logger.info(f"  {only_company}_th  ← {n} default articles (no company-specific data)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Index solutions_faq.csv into Qdrant per company")
    parser.add_argument("--file",    default=DEFAULT_CSV, help=f"Source CSV (default: {DEFAULT_CSV})")
    parser.add_argument("--company", default="",          help="Index one specific company only")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"File not found: {args.file}")
        print("Run first:  python indexers/convert_solutions_json.py --file ~/Downloads/Solutions.json")
        raise SystemExit(1)

    all_rows = _read_csv(args.file)
    defaults = sum(1 for r in all_rows if _is_default(r))
    companies = len({r["company_id"] for r in all_rows if not _is_default(r)})
    print(f"Source: {args.file}  ({len(all_rows)} rows — {defaults} defaults, {len(all_rows)-defaults} company-specific across {companies} companies)")
    print()

    index_all(args.file, only_company=args.company)

    print()
    print("Done. Collections created:")
    print("  salary_hero_th  ← defaults only  (used when tenant has no specific collection)")
    print("  {company}_th    ← company-specific + defaults merged")


if __name__ == "__main__":
    main()
