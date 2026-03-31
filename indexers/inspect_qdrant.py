"""
Qdrant inspector — debug utility.

Shows collections, record counts, and sample vectors.

Usage:
    python indexers/inspect_qdrant.py
    python indexers/inspect_qdrant.py --collection hns_th
"""

import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()


def _get_client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_HOST", "localhost"),
        api_key=os.getenv("QDRANT_API_KEY"),
        prefer_grpc=False,
    )


def list_collections() -> None:
    """Print all collections and their record counts."""
    client = _get_client()
    collections = client.get_collections().collections

    if not collections:
        print("No collections found.")
        return

    print(f"\n{'Collection':<25} {'Records':>10}")
    print("-" * 37)
    for col in collections:
        info = client.get_collection(col.name)
        count = info.points_count or 0
        print(f"{col.name:<25} {count:>10}")
    print()


def inspect_collection(collection_name: str, limit: int = 5) -> None:
    """Print sample records from a collection."""
    client = _get_client()
    results = client.scroll(collection_name=collection_name, limit=limit, with_payload=True, with_vectors=False)
    points = results[0]

    if not points:
        print(f"No records in '{collection_name}'.")
        return

    print(f"\nSample records from '{collection_name}':\n")
    for point in points:
        p = point.payload or {}
        print(f"  [{point.id}] Q: {p.get('question', '')[:60]}")
        print(f"       A: {p.get('answer', '')[:80]}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect Qdrant vector DB")
    parser.add_argument("--collection", help="Specific collection to inspect")
    parser.add_argument("--limit", type=int, default=5, help="Number of sample records")
    args = parser.parse_args()

    if args.collection:
        inspect_collection(args.collection, args.limit)
    else:
        list_collections()
