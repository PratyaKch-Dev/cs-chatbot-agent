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
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from rag.embeddings import EMBEDDING_DIM, embed_documents
from rag.query_cleaner import clean_query

logging.basicConfig(level=logging.INFO)

CSV_COLUMNS = ["Context", "Question", "Answer", "source_type", "company_id", "incident", "tags", "followup_questions"]


def _get_qdrant_client() -> QdrantClient:
    host = os.getenv("QDRANT_HOST", "localhost")
    api_key = os.getenv("QDRANT_API_KEY")
    return QdrantClient(url=host, api_key=api_key, prefer_grpc=False)


def index_csv(file_path: str, company_id: str, language: str = "th") -> int:
    """
    Index a FAQ CSV into Qdrant.
    Collection name follows convention: {company_id}_{language}
    Returns the number of records indexed.
    """
    rows = _read_csv(file_path)
    if not rows:
        logging.warning(f"No rows found in {file_path}")
        return 0

    collection = f"{company_id}_{language}"
    client = _get_qdrant_client()

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logging.info(f"Created collection: {collection}")

    texts = [
        clean_query(f"{row.get('Context', '')} {row.get('Question', '')}", language)
        for row in rows
    ]
    vectors = embed_documents(texts)

    points = [
        PointStruct(
            id=i,
            vector=vector,
            payload={
                "context": row.get("Context", ""),
                "question": row.get("Question", ""),
                "answer": row.get("Answer", ""),
                "source_type": row.get("source_type", ""),
                "company_id": row.get("company_id", company_id),
                "incident": row.get("incident", ""),
                "tags": row.get("tags", ""),
                "followup_questions": row.get("followup_questions", ""),
            },
        )
        for i, (row, vector) in enumerate(zip(rows, vectors))
    ]

    client.upsert(collection_name=collection, points=points)
    logging.info(f"Indexed {len(points)} records → {collection}")
    return len(points)


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
