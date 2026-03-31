"""Unit tests for embedding generation."""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np


class TestEmbedDocuments:
    def test_returns_list_of_vectors(self):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 512, [0.2] * 512])

        with patch("rag.embeddings.get_model", return_value=mock_model):
            from rag.embeddings import embed_documents
            result = embed_documents(["doc one", "doc two"])

        assert len(result) == 2
        assert len(result[0]) == 512
        assert isinstance(result[0][0], float)

    def test_empty_input(self):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([]).reshape(0, 512)

        with patch("rag.embeddings.get_model", return_value=mock_model):
            from rag.embeddings import embed_documents
            result = embed_documents([])

        assert result == []


class TestEmbedQuery:
    def test_returns_vector(self):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5] * 512])

        with patch("rag.embeddings.get_model", return_value=mock_model):
            # Clear LRU cache before test
            from rag.embeddings import get_embedding_cached
            get_embedding_cached.cache_clear()

            from rag.embeddings import embed_query
            result = embed_query("test query")

        assert len(result) == 512
        assert isinstance(result, list)
        assert isinstance(result[0], float)

    def test_cache_hit(self):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5] * 512])

        with patch("rag.embeddings.get_model", return_value=mock_model):
            from rag.embeddings import get_embedding_cached, embed_query
            get_embedding_cached.cache_clear()

            embed_query("same query")
            embed_query("same query")

        # model.encode should only be called once due to LRU cache
        assert mock_model.encode.call_count == 1
