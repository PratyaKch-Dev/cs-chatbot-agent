"""
Qdrant inspector — debug utility.

Shows collections, record counts, and sample vectors.

Usage:
    python indexers/inspect_qdrant.py
    python indexers/inspect_qdrant.py --collection hns_th
"""

import argparse
import os

# TODO Phase 2: import qdrant_client
# from qdrant_client import QdrantClient


def list_collections() -> None:
    """Print all collections and their record counts.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


def inspect_collection(collection_name: str, limit: int = 5) -> None:
    """Print sample records from a collection.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect Qdrant vector DB")
    parser.add_argument("--collection", help="Specific collection to inspect")
    parser.add_argument("--limit", type=int, default=5, help="Number of sample records")
    args = parser.parse_args()

    if args.collection:
        inspect_collection(args.collection, args.limit)
    else:
        list_collections()
