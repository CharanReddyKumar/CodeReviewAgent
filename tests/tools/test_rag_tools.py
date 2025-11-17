"""Tests for tools/rag_tools.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from tools.rag_tools import (
    register_repo_path,
    fetch_code_context,
    fetch_doc_context,
    fetch_best_practices,
    fetch_import_context,
    build_structured_context,
    fetch_tagged_context,
    _get_retriever,
    _chunk_to_dict,
    _REGISTERED_PATHS,
)


class TestRegisterRepoPath:
    """Tests for register_repo_path function."""

    @patch("tools.rag_tools._get_retriever")
    @patch("tools.rag_tools.normalize_repo_reference")
    def test_register_repo_path(self, mock_normalize, mock_get_retriever, temp_dir):
        """Test registering repo path."""
        mock_normalize.return_value = "test/repo"
        mock_retriever = MagicMock()
        mock_get_retriever.return_value = mock_retriever
        
        register_repo_path("test/repo", temp_dir)
        
        mock_normalize.assert_called_once_with("test/repo")
        mock_retriever.set_repo_path.assert_called_once()

    @patch("tools.rag_tools._get_retriever")
    @patch("tools.rag_tools.normalize_repo_reference")
    def test_register_repo_path_handles_exception(self, mock_normalize, mock_get_retriever, temp_dir):
        """Test registering repo path handles exceptions."""
        mock_normalize.return_value = "test/repo"
        mock_retriever = MagicMock()
        mock_retriever.set_repo_path.side_effect = Exception("Error")
        mock_get_retriever.return_value = mock_retriever
        
        # Should not raise exception
        register_repo_path("test/repo", temp_dir)


class TestChunkToDict:
    """Tests for _chunk_to_dict helper."""

    def test_chunk_to_dict(self):
        """Test converting chunk to dictionary."""
        chunk = Mock()
        chunk.text = "sample code"
        chunk.metadata = {"file": "test.py"}
        chunk.score = 0.95
        
        result = _chunk_to_dict(chunk)
        
        assert result["text"] == "sample code"
        assert result["metadata"] == {"file": "test.py"}
        assert result["score"] == 0.95


class TestFetchCodeContext:
    """Tests for fetch_code_context function."""

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_code_context(self, mock_get_retriever):
        """Test fetching code context."""
        mock_chunk = Mock()
        mock_chunk.text = "def hello():"
        mock_chunk.metadata = {"file": "test.py"}
        mock_chunk.score = 0.9
        
        mock_retriever = MagicMock()
        mock_retriever.search_code.return_value = [mock_chunk]
        mock_get_retriever.return_value = mock_retriever
        
        result = fetch_code_context("test/repo", "hello function")
        
        assert len(result) == 1
        assert result[0]["text"] == "def hello():"
        mock_retriever.search_code.assert_called_once_with("hello function", n_results=5)

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_code_context_custom_n_results(self, mock_get_retriever):
        """Test fetching code context with custom n_results."""
        mock_retriever = MagicMock()
        mock_retriever.search_code.return_value = []
        mock_get_retriever.return_value = mock_retriever
        
        fetch_code_context("test/repo", "query", n_results=10)
        
        mock_retriever.search_code.assert_called_once_with("query", n_results=10)


class TestFetchDocContext:
    """Tests for fetch_doc_context function."""

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_doc_context(self, mock_get_retriever):
        """Test fetching documentation context."""
        mock_chunk = Mock()
        mock_chunk.text = "# Documentation"
        mock_chunk.metadata = {"file": "README.md"}
        mock_chunk.score = 0.85
        
        mock_retriever = MagicMock()
        mock_retriever.search_documentation.return_value = [mock_chunk]
        mock_get_retriever.return_value = mock_retriever
        
        result = fetch_doc_context("test/repo", "readme")
        
        assert len(result) == 1
        assert result[0]["text"] == "# Documentation"


class TestFetchBestPractices:
    """Tests for fetch_best_practices function."""

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_best_practices(self, mock_get_retriever):
        """Test fetching best practices."""
        mock_chunk = Mock()
        mock_chunk.text = "Best practice: use type hints"
        mock_chunk.metadata = {"source": "pep8"}
        mock_chunk.score = 0.95
        
        mock_retriever = MagicMock()
        mock_retriever.search_best_practices.return_value = [mock_chunk]
        mock_get_retriever.return_value = mock_retriever
        
        result = fetch_best_practices("test/repo", "type hints")
        
        assert len(result) == 1
        assert "type hints" in result[0]["text"]


class TestFetchImportContext:
    """Tests for fetch_import_context function."""

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_import_context(self, mock_get_retriever):
        """Test fetching import context."""
        mock_subgraph = Mock()
        mock_subgraph.nodes = ["module_a", "module_b"]
        mock_subgraph.edges = [("module_a", "module_b")]
        
        mock_retriever = MagicMock()
        mock_retriever.import_neighborhood.return_value = mock_subgraph
        mock_get_retriever.return_value = mock_retriever
        
        result = fetch_import_context("test/repo", "module_a")
        
        assert result is not None
        assert result["nodes"] == ["module_a", "module_b"]
        assert len(result["edges"]) == 1

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_import_context_none(self, mock_get_retriever):
        """Test fetching import context returns None when not found."""
        mock_retriever = MagicMock()
        mock_retriever.import_neighborhood.return_value = None
        mock_get_retriever.return_value = mock_retriever
        
        result = fetch_import_context("test/repo", "nonexistent")
        
        assert result is None

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_import_context_custom_depth(self, mock_get_retriever):
        """Test fetching import context with custom depth."""
        mock_retriever = MagicMock()
        mock_retriever.import_neighborhood.return_value = None
        mock_get_retriever.return_value = mock_retriever
        
        fetch_import_context("test/repo", "module", depth=2)
        
        mock_retriever.import_neighborhood.assert_called_once_with("module", depth=2)


class TestBuildStructuredContext:
    """Tests for build_structured_context function."""

    @patch("tools.rag_tools._get_retriever")
    def test_build_structured_context(self, mock_get_retriever):
        """Test building structured context."""
        mock_retriever = MagicMock()
        mock_retriever.build_context_bundle.return_value = {
            "file_path": "test.py",
            "context": "sample"
        }
        mock_get_retriever.return_value = mock_retriever
        
        result = build_structured_context(
            "test/repo",
            "test.py",
            "patch text",
            "query"
        )
        
        assert result["file_path"] == "test.py"
        mock_retriever.build_context_bundle.assert_called_once()

    @patch("tools.rag_tools._get_retriever")
    def test_build_structured_context_with_risk_tags(self, mock_get_retriever):
        """Test building structured context with risk tags."""
        mock_retriever = MagicMock()
        mock_retriever.build_context_bundle.return_value = {}
        mock_get_retriever.return_value = mock_retriever
        
        build_structured_context(
            "test/repo",
            "test.py",
            "patch",
            "query",
            risk_tags=["security", "performance"]
        )
        
        call_kwargs = mock_retriever.build_context_bundle.call_args[1]
        assert call_kwargs["risk_tags"] == ["security", "performance"]


class TestFetchTaggedContext:
    """Tests for fetch_tagged_context function."""

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_tagged_context(self, mock_get_retriever):
        """Test fetching tagged context."""
        mock_retriever = MagicMock()
        mock_retriever.tagged_search.return_value = [
            {"text": "tagged content", "tags": ["security"]}
        ]
        mock_get_retriever.return_value = mock_retriever
        
        result = fetch_tagged_context("test/repo", "auth")
        
        assert len(result) == 1
        mock_retriever.tagged_search.assert_called_once()

    @patch("tools.rag_tools._get_retriever")
    def test_fetch_tagged_context_with_filters(self, mock_get_retriever):
        """Test fetching tagged context with filters."""
        mock_retriever = MagicMock()
        mock_retriever.tagged_search.return_value = []
        mock_get_retriever.return_value = mock_retriever
        
        fetch_tagged_context(
            "test/repo",
            "query",
            kinds=["code"],
            risk_domains=["security"],
            limit=10
        )
        
        call_kwargs = mock_retriever.tagged_search.call_args[1]
        assert call_kwargs["kinds"] == ["code"]
        assert call_kwargs["risk_domains"] == ["security"]
        assert call_kwargs["limit"] == 10
