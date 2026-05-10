"""
RAG retrieval pipeline.

Full pipeline:
    clean query → embed (cached) → vector search → rerank → build context
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from rag.embeddings import embed_query
from rag.query_cleaner import clean_query
from rag.reranker import rerank

load_dotenv()

VECTOR_SEARCH_TOP_K = 25
RERANK_TOP_K = 3
RERANK_MIN_SCORE = 0.3   # below this → no useful match found

_qdrant_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=os.getenv("QDRANT_HOST", "localhost"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=False,
        )
    return _qdrant_client


@dataclass
class RetrievedDocument:
    question: str
    answer: str
    context: str
    source_type: str            # faq | incident | company
    company_id: str
    score: float
    tags: list[str] = field(default_factory=list)
    followup_questions: list[str] = field(default_factory=list)
    incident: str = ""
    image_urls: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    documents: list[RetrievedDocument]
    query_used: str
    collection: str
    reranked: bool = False


def retrieve(
    query: str,
    tenant_id: str,
    language: str,
    top_k: int = RERANK_TOP_K,
) -> RetrievalResult:
    """Run the full RAG retrieval pipeline for a query."""
    collection = _get_collection_name(tenant_id, language)
    cleaned = clean_query(query, language)
    vector = embed_query(cleaned)

    client = _get_client()
    try:
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=VECTOR_SEARCH_TOP_K,
            with_payload=True,
        )
    except Exception as e:
        # Language collection missing → fall back to Thai (multilingual embeddings work cross-language)
        fallback = _get_collection_name(tenant_id, "th")
        if language != "th" and fallback != collection:
            logging.warning(
                f"[retriever] collection {collection!r} not found ({e}), "
                f"falling back to {fallback!r}"
            )
            collection = fallback
            hits = client.search(
                collection_name=collection,
                query_vector=vector,
                limit=VECTOR_SEARCH_TOP_K,
                with_payload=True,
            )
        else:
            logging.warning(f"[retriever] search failed for {collection!r}: {e}")
            return RetrievalResult(documents=[], query_used=cleaned, collection=collection)

    if not hits:
        return RetrievalResult(documents=[], query_used=cleaned, collection=collection)

    # Build text representations for reranker
    doc_texts = [
        f"{h.payload.get('question', '')} {h.payload.get('answer', '')}"
        for h in hits
    ]

    reranked = rerank(query=cleaned, documents=doc_texts, top_k=top_k)

    # If the best reranker score is too low, the question doesn't match any FAQ article
    if reranked and reranked[0].score < RERANK_MIN_SCORE:
        logging.info(f"Best rerank score {reranked[0].score:.3f} < {RERANK_MIN_SCORE} — no useful match")
        return RetrievalResult(documents=[], query_used=cleaned, collection=collection)

    documents = []
    for result in reranked:
        payload = hits[result.index].payload or {}
        tags_raw = payload.get("tags", "")
        followup_raw = payload.get("followup_questions", "")
        imgs_raw = payload.get("image_urls", "")
        documents.append(RetrievedDocument(
            question=payload.get("question", ""),
            answer=payload.get("answer", ""),
            context=payload.get("context", ""),
            source_type=payload.get("source_type", ""),
            company_id=payload.get("company_id", tenant_id),
            score=result.score,
            tags=[t.strip() for t in tags_raw.split(";") if t.strip()] if tags_raw else [],
            followup_questions=[f.strip() for f in followup_raw.split(";") if f.strip()] if followup_raw else [],
            incident=payload.get("incident", ""),
            image_urls=[u.strip() for u in imgs_raw.split(";") if u.strip()] if imgs_raw else [],
        ))

    logging.info(f"Retrieved {len(documents)} docs from {collection} for query: {cleaned[:50]}")
    return RetrievalResult(documents=documents, query_used=cleaned, collection=collection, reranked=True)


def build_context(documents: list[RetrievedDocument], language: str) -> str:
    """Assemble retrieved documents into an LLM-ready context string."""
    if not documents:
        return ""

    parts = []
    for i, doc in enumerate(documents, 1):
        parts.append(
            f"[{i}] Q: {doc.question}\n"
            f"    A: {doc.answer}"
        )

    return "\n\n".join(parts)


_TENANTS_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "tenants.yaml")
_tenants_cache: dict | None = None


def _load_tenants() -> dict:
    """Load tenants.yaml once and cache."""
    global _tenants_cache
    if _tenants_cache is None:
        try:
            import yaml
            with open(_TENANTS_CONFIG, encoding="utf-8") as f:
                _tenants_cache = (yaml.safe_load(f) or {}).get("tenants", {})
        except Exception as e:
            logging.warning(f"[retriever] failed to load tenants.yaml: {e}")
            _tenants_cache = {}
    return _tenants_cache


def _get_collection_name(tenant_id: str, language: str) -> str:
    """
    Resolve Qdrant collection name from tenants.yaml `vector_collections`.
    Falls back to `{tenant_id}_{language}` if not configured.
    """
    tenants = _load_tenants()
    cfg = tenants.get(tenant_id, {})
    collections = cfg.get("vector_collections", {})
    return collections.get(language) or f"{tenant_id}_{language}"
