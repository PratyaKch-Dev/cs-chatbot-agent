"""
BGE Reranker.

Re-scores retrieved documents using cross-encoder model.
Filters out documents below score threshold.
"""

import logging
import math
import os
from dataclasses import dataclass

from sentence_transformers import CrossEncoder

MODEL_NAME = "BAAI/bge-reranker-base"
DEFAULT_THRESHOLD = 0.3
DEFAULT_TOP_K = 5

_model: CrossEncoder | None = None


@dataclass
class RerankResult:
    index: int          # original index in input list
    score: float        # sigmoid-normalized score (0–1)
    text: str


def get_reranker_model() -> CrossEncoder:
    """Lazy-load and return the CrossEncoder model singleton."""
    global _model
    if _model is None:
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        logging.info(f"Loading reranker model: {MODEL_NAME}")
        _model = CrossEncoder(MODEL_NAME)
    return _model


def rerank(
    query: str,
    documents: list[str],
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[RerankResult]:
    """
    Rerank documents against the query using BGE cross-encoder.

    Steps:
    1. Score all (query, doc) pairs
    2. Apply sigmoid normalization
    3. Filter scores below threshold
    4. Return top_k by score
    """
    if not documents:
        return []

    model = get_reranker_model()
    pairs = [[query, doc] for doc in documents]
    raw_scores = model.predict(pairs)

    results = [
        RerankResult(index=i, score=_sigmoid(float(score)), text=doc)
        for i, (doc, score) in enumerate(zip(documents, raw_scores))
    ]

    results = [r for r in results if r.score >= threshold]
    results.sort(key=lambda r: r.score, reverse=True)

    if not results:
        logging.warning("No reranked results above threshold — returning top_k anyway")
        results = sorted(
            [RerankResult(index=i, score=_sigmoid(float(s)), text=d)
             for i, (d, s) in enumerate(zip(documents, raw_scores))],
            key=lambda r: r.score, reverse=True,
        )

    return results[:top_k]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
