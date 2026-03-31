"""
Embedding generation.

Wraps SentenceTransformer with:
- LRU cache (500 entries) for query embeddings
- Batch processing for document embeddings
"""

from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = "distiluse-base-multilingual-cased-v2"
EMBEDDING_DIM = 512
BATCH_SIZE = 16

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Lazy-load and return the SentenceTransformer model singleton."""
    global _model
    if _model is None:
        print(f"Loading embedding model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


@lru_cache(maxsize=500)
def get_embedding_cached(text: str) -> tuple[float, ...]:
    """
    Embed a single query string with LRU caching.
    Returns a tuple (hashable) for cache compatibility.
    """
    vector = get_model().encode([text], show_progress_bar=False, convert_to_numpy=True)
    return tuple(vector[0].tolist())


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents (no cache — documents are indexed offline)."""
    print(f"Encoding {len(texts)} documents...")
    vectors = get_model().encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a single query string (uses LRU cache internally)."""
    return list(get_embedding_cached(text))
