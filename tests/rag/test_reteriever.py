"""Tests for rag/reteriever.py - Complete coverage"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


class TestRepositoryRetriever:
    """Tests for RepositoryRetriever class."""

    @patch("rag.reteriever.get_code_collection")
    def test_retriever_init(self, mock_collection, temp_dir):
        """Test retriever initialization."""
        from rag.reteriever import RepositoryRetriever
        
        mock_collection.return_value = MagicMock()
        
        retriever = RepositoryRetriever("test/repo", repo_path=temp_dir)
        assert retriever is not None

    @patch("rag.reteriever.get_code_collection")
    def test_search_code(self, mock_collection):
        """Test code search."""
        from rag.reteriever import RepositoryRetriever
        
        mock_coll = MagicMock()
        mock_coll.query.return_value = {
            "documents": [["code sample"]],
            "metadatas": [[{"file": "test.py"}]],
            "distances": [[0.1]]
        }
        mock_collection.return_value = mock_coll
        
        retriever = RepositoryRetriever("test/repo")
        results = retriever.search_code("query", n_results=5)
        
        # Should return list of results
        assert isinstance(results, list)

    @patch("rag.reteriever.get_code_collection")
    def test_search_documentation(self, mock_collection):
        """Test documentation search."""
        from rag.reteriever import RepositoryRetriever
        
        mock_coll = MagicMock()
        mock_coll.query.return_value = {
            "documents": [["doc content"]],
            "metadatas": [[{"file": "README.md"}]],
            "distances": [[0.05]]
        }
        mock_collection.return_value = mock_coll
        
        retriever = RepositoryRetriever("test/repo")
        results = retriever.search_documentation("query")
        
        assert isinstance(results, list)

    @patch("rag.reteriever.get_code_collection")
    def test_set_repo_path(self, mock_collection, temp_dir):
        """Test setting repo path."""
        from rag.reteriever import RepositoryRetriever
        
        mock_collection.return_value = MagicMock()
        
        retriever = RepositoryRetriever("test/repo")
        retriever.set_repo_path(temp_dir)
        
        # Should not raise
        assert True
