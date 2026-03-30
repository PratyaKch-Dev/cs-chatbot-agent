"""
RAG retrieval pipeline.

Full pipeline:
    clean query → embed (cached) → vector search → rerank → build context
"""

from dataclasses import dataclass, field
from typing import Optional

from rag.embeddings import get_embedding_cached
from rag.reranker import rerank
from rag.query_cleaner import clean_query

# TODO Phase 2: import vector DB client
# from qdrant_client import QdrantClient

VECTOR_SEARCH_TOP_K = 10
RERANK_TOP_K = 5


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
    """
    Run the full RAG retrieval pipeline for a query.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


def build_context(documents: list[RetrievedDocument], language: str) -> str:
    """
    Assemble retrieved documents into an LLM-ready context string.
    Injects active incidents if applicable.

    TODO Phase 2: implement.
    """
    raise NotImplementedError("Phase 2")


def _get_collection_name(tenant_id: str, language: str) -> str:
    """Returns Qdrant collection name: {company_id}_{language}"""
    return f"{tenant_id}_{language}"
