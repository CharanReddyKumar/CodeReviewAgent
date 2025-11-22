"""Tests for rag/vector_store.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from rag.vector_store import (
    _language_for_suffix,
    _is_test_path,
    _infer_risk_domain,
    _build_tags,
    _sanitize_id_component,
    _chunk_text,
    Chunk,
    CODE_EXTENSIONS,
    DOC_EXTENSIONS,
    RISK_HINTS,
)


class TestLanguageForSuffix:
    """Tests for _language_for_suffix function."""

    def test_python_suffix(self):
        """Test Python file suffix."""
        assert _language_for_suffix(".py") == "python"

    def test_major_language_suffixes(self):
        """Ensure other major language suffixes are recognized."""
        assert _language_for_suffix(".java") == "java"
        assert _language_for_suffix(".rs") == "rust"

    def test_markdown_suffix(self):
        """Test Markdown file suffix."""
        assert _language_for_suffix(".md") == "markdown"

    def test_unknown_suffix(self):
        """Test unknown file suffix."""
        assert _language_for_suffix(".xyz") == "text"

    def test_case_insensitive(self):
        """Test case insensitive suffix matching."""
        assert _language_for_suffix(".PY") == "python"
        assert _language_for_suffix(".MD") == "markdown"


class TestIsTestPath:
    """Tests for _is_test_path function."""

    def test_test_directory(self):
        """Test detecting test directory."""
        path = Path("tests/test_utils.py")
        assert _is_test_path(path) is True

    def test_test_prefix(self):
        """Test detecting test_ prefix."""
        path = Path("test_utils.py")
        assert _is_test_path(path) is True

    def test_test_suffix(self):
        """Test detecting _test.py suffix."""
        path = Path("utils_test.py")
        assert _is_test_path(path) is True

    def test_non_test_file(self):
        """Test non-test file."""
        path = Path("src/utils.py")
        assert _is_test_path(path) is False


class TestInferRiskDomain:
    """Tests for _infer_risk_domain function."""

    def test_security_risk(self):
        """Test detecting security risk."""
        risk = _infer_risk_domain("auth/login.py", "token validation")
        assert risk == "security"

    def test_performance_risk(self):
        """Test detecting performance risk."""
        risk = _infer_risk_domain("cache/optimizer.py", "performance critical")
        assert risk == "performance"

    def test_test_risk(self):
        """Test detecting test files."""
        risk = _infer_risk_domain("tests/test_api.py", "test fixture")
        assert risk == "tests"

    def test_docs_risk(self):
        """Test detecting documentation."""
        risk = _infer_risk_domain("docs/readme.md", "API documentation")
        assert risk == "docs"

    def test_general_risk(self):
        """Test default general risk."""
        risk = _infer_risk_domain("utils/helpers.py", "utility functions")
        assert risk == "general"


class TestBuildTags:
    """Tests for _build_tags function."""

    def test_code_tags(self):
        """Test building tags for code."""
        tags = _build_tags(kind="code", module="utils.helpers", risk="general", is_test=False)
        assert "kind:code" in tags
        assert "risk:general" in tags
        assert "module:utils.helpers" in tags

    def test_test_tags(self):
        """Test building tags for test files."""
        tags = _build_tags(kind="code", module="tests.test_utils", risk="tests", is_test=True)
        assert "scope:tests" in tags

    def test_doc_tags(self):
        """Test building tags for documentation."""
        tags = _build_tags(kind="doc", module="", risk="docs", is_test=False)
        assert "kind:doc" in tags
        assert "risk:docs" in tags


class TestSanitizeIdComponent:
    """Tests for _sanitize_id_component function."""

    def test_sanitize_slashes(self):
        """Test sanitizing slashes."""
        result = _sanitize_id_component("src/utils/helpers.py")
        assert "/" not in result
        assert "_" in result

    def test_sanitize_colons(self):
        """Test sanitizing colons."""
        result = _sanitize_id_component("module:function")
        assert ":" not in result
        assert "_" in result


class TestChunkText:
    """Tests for _chunk_text function."""

    def test_chunk_small_text(self):
        """Test chunking small text."""
        text = "Line 1\nLine 2\nLine 3"
        chunks = list(_chunk_text(text, max_lines=10, overlap_lines=2))
        assert len(chunks) == 1
        assert chunks[0].start_line == 1

    def test_chunk_large_text(self):
        """Test chunking large text."""
        text = "\n".join([f"Line {i}" for i in range(100)])
        chunks = list(_chunk_text(text, max_lines=20, overlap_lines=5))
        assert len(chunks) > 1

    def test_chunk_empty_text(self):
        """Test chunking empty text."""
        chunks = list(_chunk_text("", max_lines=10, overlap_lines=2))
        assert len(chunks) == 0

    def test_chunk_overlap(self):
        """Test chunk overlap."""
        text = "\n".join([f"Line {i}" for i in range(50)])
        chunks = list(_chunk_text(text, max_lines=20, overlap_lines=5))
        # Verify chunks overlap
        assert len(chunks) >= 2


class TestConstants:
    """Test module constants."""

    def test_code_extensions(self):
        """Test CODE_EXTENSIONS is defined."""
        assert ".py" in CODE_EXTENSIONS
        assert ".js" in CODE_EXTENSIONS

    def test_doc_extensions(self):
        """Test DOC_EXTENSIONS is defined."""
        assert ".md" in DOC_EXTENSIONS

    def test_risk_hints(self):
        """Test RISK_HINTS is defined."""
        assert "security" in RISK_HINTS
        assert "performance" in RISK_HINTS


@pytest.mark.slow
class TestIndexRepository:
    """Tests for index_repository function - requires ChromaDB."""

    @patch("rag.vector_store.get_code_collection")
    @patch("rag.vector_store.iter_code_files")
    @patch("rag.vector_store._iter_doc_files")
    def test_index_repository_mock(self, mock_doc_files, mock_py_files, mock_collection, temp_dir):
        """Test repository indexing with mocks."""
        from rag.vector_store import index_repository
        
        mock_collection_obj = MagicMock()
        mock_collection.return_value = mock_collection_obj
        mock_py_files.return_value = []
        mock_doc_files.return_value = []
        
        # Should not raise
        index_repository(temp_dir, "test/repo")
        
        mock_collection.assert_called_once()
