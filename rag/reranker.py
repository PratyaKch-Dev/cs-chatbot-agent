"""
BGE Reranker.

Re-scores retrieved documents using cross-encoder model.
Filters out documents below score threshold.
"""

import math
from dataclasses import dataclass

MODEL_NAME = "BAAI/bge-reranker-base"
DEFAULT_THRESHOLD = 0.3
DEFAULT_TOP_K = 5

# TODO Phase 2: lazy-load model
# from sentence_transformers import CrossEncoder
# _model: CrossEncoder | None = None


@dataclass
class RerankResult:
    index: int          # original index in input list
    score: float        # sigmoid-normalized score (0–1)
    text: str


def get_reranker_model():
    """Lazy-load and return the CrossEncoder model singleton.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


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

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
