"""Tests for agents/context_agent.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from agents.context_agent import ContextAgent, _module_name_from_path
from agents.review_types import ReviewManifest, ContextPacket


class TestModuleNameFromPath:
    """Tests for _module_name_from_path function."""

    def test_python_file_path(self):
        """Test extracting module name from Python file."""
        result = _module_name_from_path("src/utils/helpers.py")
        assert result == "src.utils.helpers"

    def test_nested_path(self):
        """Test extracting module name from nested path."""
        result = _module_name_from_path("app/services/auth/login.py")
        assert result == "app.services.auth.login"

    def test_no_extension(self):
        """Test path without extension."""
        result = _module_name_from_path("src/module")
        assert result == ""

    def test_root_file(self):
        """Test root level file."""
        result = _module_name_from_path("app.py")
        assert result == "app"

    def test_javascript_file(self):
        """Test JavaScript file path."""
        result = _module_name_from_path("src/app.js")
        assert result == "src.app"


class TestContextAgent:
    """Tests for ContextAgent class."""

    def test_init(self):
        """Test ContextAgent initialization."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever,
            repo_path=Path("/repo")
        )
        
        assert agent.repo_reference == "github.com/user/repo"
        assert agent.retriever == mock_retriever
        assert agent.repo_path == Path("/repo")
        assert agent.max_patch_chars == 4000

    @patch("agents.context_agent.rag_tools")
    def test_build_context_packets_basic(self, mock_rag_tools):
        """Test building basic context packets."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever
        )
        
        manifest: ReviewManifest = {
            "summary": "Test change",
            "components": ["auth"],
            "high_risk_tags": ["security"],
            "files": ["auth.py"],
            "languages": ["python"],
            "frameworks": [],
            "size": "small",
            "priority": "medium",
            "description": "Test"
        }
        
        file_context = Mock()
        file_context.file_path = "auth.py"
        file_context.patch_text = "diff content"
        file_context.context = {}
        
        # Mock RAG tools
        mock_rag_tools.fetch_code_context.return_value = []
        mock_rag_tools.fetch_doc_context.return_value = []
        mock_rag_tools.fetch_best_practices.return_value = []
        mock_rag_tools.fetch_import_context.return_value = []
        
        packets = agent.build_context_packets(manifest, [file_context])
        
        assert len(packets) == 1
        assert packets[0]["file_path"] == "auth.py"
        assert packets[0]["module"] == "auth"

    @patch("agents.context_agent.rag_tools")
    def test_build_context_packets_with_rag_data(self, mock_rag_tools):
        """Test building context packets with RAG data."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever
        )
        
        manifest: ReviewManifest = {
            "summary": "Test",
            "components": [],
            "high_risk_tags": [],
            "files": ["file.py"],
            "languages": ["python"],
            "frameworks": [],
            "size": "small",
            "priority": "medium",
            "description": "Test"
        }
        
        file_context = Mock()
        file_context.file_path = "file.py"
        file_context.patch_text = "patch"
        file_context.context = {}
        
        # Mock RAG data
        mock_rag_tools.fetch_code_context.return_value = [
            {"content": "code snippet", "metadata": {}}
        ]
        mock_rag_tools.fetch_doc_context.return_value = [
            {"content": "documentation", "metadata": {}}
        ]
        mock_rag_tools.fetch_best_practices.return_value = [
            {"content": "best practice", "metadata": {}}
        ]
        mock_rag_tools.fetch_import_context.return_value = []
        
        packets = agent.build_context_packets(manifest, [file_context])
        
        assert len(packets) == 1
        assert len(packets[0]["rag_code"]) > 0
        assert len(packets[0]["rag_docs"]) > 0
        assert len(packets[0]["rag_best_practices"]) > 0

    @patch("agents.context_agent.rag_tools")
    def test_build_context_packets_with_existing_context(self, mock_rag_tools):
        """Test building packets with existing context data."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever
        )
        
        manifest: ReviewManifest = {
            "summary": "Test",
            "components": [],
            "high_risk_tags": [],
            "files": ["file.py"],
            "languages": ["python"],
            "frameworks": [],
            "size": "small",
            "priority": "medium",
            "description": "Test"
        }
        
        file_context = Mock()
        file_context.file_path = "file.py"
        file_context.patch_text = "patch"
        file_context.context = {
            "code": [{"content": "existing code"}],
            "documentation": [{"content": "existing docs"}],
            "best_practices": [{"content": "existing bp"}],
            "imports": [{"module": "os"}]
        }
        
        packets = agent.build_context_packets(manifest, [file_context])
        
        # Should use existing context, not fetch new
        assert not mock_rag_tools.fetch_code_context.called
        assert len(packets) == 1

    @patch("agents.context_agent.rag_tools")
    def test_build_context_packets_truncates_patch(self, mock_rag_tools):
        """Test that large patches are truncated."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever
        )
        
        manifest: ReviewManifest = {
            "summary": "Test",
            "components": [],
            "high_risk_tags": [],
            "files": ["file.py"],
            "languages": ["python"],
            "frameworks": [],
            "size": "large",
            "priority": "medium",
            "description": "Test"
        }
        
        file_context = Mock()
        file_context.file_path = "file.py"
        # Create large patch
        file_context.patch_text = "a" * 10000
        file_context.context = {}
        
        mock_rag_tools.fetch_code_context.return_value = []
        mock_rag_tools.fetch_doc_context.return_value = []
        mock_rag_tools.fetch_best_practices.return_value = []
        mock_rag_tools.fetch_import_context.return_value = []
        
        packets = agent.build_context_packets(manifest, [file_context])
        
        # Patch should be truncated
        assert len(packets[0]["patch"]) <= agent.max_patch_chars

    @patch("agents.context_agent.rag_tools")
    def test_build_context_packets_multiple_files(self, mock_rag_tools):
        """Test building packets for multiple files."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever
        )
        
        manifest: ReviewManifest = {
            "summary": "Test",
            "components": [],
            "high_risk_tags": [],
            "files": ["file1.py", "file2.py"],
            "languages": ["python"],
            "frameworks": [],
            "size": "medium",
            "priority": "medium",
            "description": "Test"
        }
        
        file_contexts = []
        for i in range(2):
            fc = Mock()
            fc.file_path = f"file{i+1}.py"
            fc.patch_text = f"patch{i+1}"
            fc.context = {}
            file_contexts.append(fc)
        
        mock_rag_tools.fetch_code_context.return_value = []
        mock_rag_tools.fetch_doc_context.return_value = []
        mock_rag_tools.fetch_best_practices.return_value = []
        mock_rag_tools.fetch_import_context.return_value = []
        
        packets = agent.build_context_packets(manifest, file_contexts)
        
        assert len(packets) == 2
        assert packets[0]["id"] == "ctx_0"
        assert packets[1]["id"] == "ctx_1"

    @patch("agents.context_agent.rag_tools")
    def test_build_context_packets_with_structured_context(self, mock_rag_tools):
        """Test building packets with structured context."""
        mock_retriever = Mock()
        agent = ContextAgent(
            repo_reference="github.com/user/repo",
            retriever=mock_retriever
        )
        
        manifest: ReviewManifest = {
            "summary": "Test",
            "components": [],
            "high_risk_tags": [],
            "files": ["file.py"],
            "languages": ["python"],
            "frameworks": [],
            "size": "small",
            "priority": "medium",
            "description": "Test"
        }
        
        file_context = Mock()
        file_context.file_path = "file.py"
        file_context.patch_text = "patch"
        file_context.context = {
            "structured": {
                "scoped_code": [{"content": "structured code"}],
                "scoped_docs": [{"content": "structured docs"}],
                "related_tests": [{"file_path": "test_file.py"}],
                "symbol_context": [{"name": "MyClass"}],
                "lexical_hits": [{"line": 42}]
            }
        }
        
        packets = agent.build_context_packets(manifest, [file_context])
        
        assert len(packets) == 1
        assert "test_file.py" in packets[0]["tests"]
        assert len(packets[0]["symbol_context"]) > 0
        assert len(packets[0]["lexical_context"]) > 0
