"""Tests for agents/intake_agent.py - Complete coverage"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from agents.intake_agent import IntakeAgent


class TestIntakeAgent:
    """Tests for IntakeAgent class."""

    @patch("agents.intake_agent.build_chat_model")
    def test_init(self, mock_build_chat):
        """Test IntakeAgent initialization."""
        mock_chat = MagicMock()
        mock_build_chat.return_value = mock_chat
        
        agent = IntakeAgent()
        
        mock_build_chat.assert_called_once_with(task="intake")
        assert agent.chat == mock_chat

    @patch("agents.intake_agent.build_chat_model")
    def test_create_manifest_success(self, mock_build_chat):
        """Test creating manifest successfully."""
        mock_response = Mock()
        mock_response.content = '{"summary": "Test", "size": "small", "priority": "high"}'
        mock_chat = MagicMock()
        mock_chat.invoke.return_value = mock_response
        mock_build_chat.return_value = mock_chat
        
        agent = IntakeAgent()
        manifest = agent.create_manifest(
            "Test commit",
            ["file.py"],
            "diff",
            ["python"]
        )
        
        assert manifest["summary"] == "Test"
        assert manifest["size"] == "small"
        assert manifest["files"] == ["file.py"]

    @patch("agents.intake_agent.build_chat_model")
    def test_create_manifest_with_fallback(self, mock_build_chat):
        """Test creating manifest with fallback when LLM returns invalid JSON."""
        mock_response = Mock()
        mock_response.content = "Not valid JSON"
        mock_chat = MagicMock()
        mock_chat.invoke.return_value = mock_response
        mock_build_chat.return_value = mock_chat
        
        agent = IntakeAgent()
        manifest = agent.create_manifest(
            "Test commit",
            ["file.py"],
            "diff",
            ["python"]
        )
        
        assert manifest["files"] == ["file.py"]
        assert manifest["languages"] == ["python"]
        assert manifest["size"] == "medium"

    @patch("agents.intake_agent.build_chat_model")
    def test_parse_manifest_with_dict(self, mock_build_chat):
        """Test parsing manifest from dictionary."""
        agent = IntakeAgent()
        
        manifest = agent._parse_manifest(
            '{"summary": "Test", "frameworks": ["django"]}',
            ["file.py"],
            ["python"]
        )
        
        assert manifest["summary"] == "Test"
        assert "django" in manifest["frameworks"]

    @patch("agents.intake_agent.build_chat_model")
    def test_parse_manifest_defaults(self, mock_build_chat):
        """Test parse manifest returns defaults."""
        agent = IntakeAgent()
        
        manifest = agent._parse_manifest(
            "invalid",
            ["default.py"],
            ["python"]
        )
        
        assert manifest["files"] == ["default.py"]
        assert manifest["languages"] == ["python"]
        assert manifest["size"] == "medium"
