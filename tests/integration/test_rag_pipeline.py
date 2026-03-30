"""
Integration tests for the full RAG pipeline.

Requires:
- Qdrant running and populated (run index_faq_csv.py first)
- QDRANT_HOST and QDRANT_API_KEY set in environment
"""

import pytest


@pytest.mark.integration
class TestRAGPipeline:
    def test_faq_query_returns_results(self):
        """Full pipeline: query → embed → search → rerank → context."""
        # TODO Phase 2: implement
        pass

    def test_thai_query_returns_thai_results(self):
        # TODO Phase 2: implement
        pass

    def test_low_similarity_triggers_rerank(self):
        # TODO Phase 2: implement
        pass

    def test_incident_injected_in_context(self):
        # TODO Phase 3: implement — active incident should appear in context
        pass
