"""
RAG pipeline evaluation.

Offline metrics to measure retrieval quality:
- Context Precision:  what fraction of retrieved docs are relevant?
- Context Recall:     what fraction of relevant docs were retrieved?
- Faithfulness:       is the answer grounded in the context?
- Answer Relevance:   does the answer address the question?

Run manually before deploying RAG changes.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"


@dataclass
class RAGEvalResult:
    question: str
    expected_answer: str
    generated_answer: str
    retrieved_docs: list[str]
    context_precision: float
    context_recall: float
    faithfulness: float
    answer_relevance: float


def run_rag_eval(
    test_cases_path: str = str(DATASETS_DIR / "rag_test_cases.json"),
    tenant_id: str = "hns",
    language: str = "th",
) -> list[RAGEvalResult]:
    """
    Run RAG evaluation against the test dataset.

    TODO Phase 7: implement using ragas or custom scorers.
    """
    raise NotImplementedError("Phase 7")


def print_eval_report(results: list[RAGEvalResult]) -> None:
    """Print a summary report of evaluation results."""
    raise NotImplementedError("Phase 7")
