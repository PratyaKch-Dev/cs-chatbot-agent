"""
Embedding generation.

Wraps SentenceTransformer with:
- LRU cache (500 entries) for query embeddings
- Batch processing for document embeddings
"""

from functools import lru_cache
from typing import Union

MODEL_NAME = "distiluse-base-multilingual-cased-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 16

# TODO Phase 2: lazy-load model to avoid startup cost
# from sentence_transformers import SentenceTransformer
# _model: SentenceTransformer | None = None


def get_model():
    """Lazy-load and return the SentenceTransformer model singleton.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


@lru_cache(maxsize=500)
def get_embedding_cached(text: str) -> tuple[float, ...]:
    """
    Embed a single query string with LRU caching.
    Returns a tuple (hashable) for cache compatibility.

    TODO Phase 2: implement using get_model().
    """
    raise NotImplementedError("Phase 2")


def embed_documents(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of documents (no cache — documents are indexed offline).

    TODO Phase 2: implement batch encoding with BATCH_SIZE.
    """
    raise NotImplementedError("Phase 2")


def embed_query(text: str) -> list[float]:
    """Embed a single query string (uses LRU cache internally)."""
    return list(get_embedding_cached(text))
