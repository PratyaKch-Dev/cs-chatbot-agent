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
    hits = client.search(
        collection_name=collection,
        query_vector=vector,
        limit=VECTOR_SEARCH_TOP_K,
        with_payload=True,
    )

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


def _get_collection_name(tenant_id: str, language: str) -> str:
    """Returns Qdrant collection name: {company_id}_{language}"""
    return f"{tenant_id}_{language}"
