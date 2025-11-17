"""Tests for agents/triage_agent.py - Complete coverage"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from agents.triage_agent import TriageAgent, DEFAULT_LANES


class TestTriageAgent:
    """Tests for TriageAgent class."""

    @patch("agents.triage_agent.build_chat_model")
    def test_init(self, mock_build_chat):
        """Test TriageAgent initialization."""
        mock_chat = MagicMock()
        mock_build_chat.return_value = mock_chat
        
        agent = TriageAgent()
        
        mock_build_chat.assert_called_once_with(task="triage")
        assert agent.chat == mock_chat

    @patch("agents.triage_agent.build_chat_model")
    def test_run_triage_success(self, mock_build_chat):
        """Test running triage successfully."""
        mock_response = Mock()
        mock_response.content = '''{
            "overall_risk": "high",
            "lanes": ["security", "tests"],
            "decisions": [],
            "recommendations": ["Review auth logic"]
        }'''
        mock_chat = MagicMock()
        mock_chat.invoke.return_value = mock_response
        mock_build_chat.return_value = mock_chat
        
        agent = TriageAgent()
        plan = agent.run_triage(
            {"summary": "Test"},
            [],
            "diff"
        )
        
        assert plan["overall_risk"] == "high"
        assert "security" in plan["lanes"]

    @patch("agents.triage_agent.build_chat_model")
    def test_run_triage_with_fallback(self, mock_build_chat):
        """Test triage with fallback."""
        mock_response = Mock()
        mock_response.content = "Invalid JSON"
        mock_chat = MagicMock()
        mock_chat.invoke.return_value = mock_response
        mock_build_chat.return_value = mock_chat
        
        agent = TriageAgent()
        manifest = {"priority": "high", "summary": "Test"}
        packets = [{"file_path": "test.py"}]
        
        plan = agent.run_triage(manifest, packets, "diff")
        
        assert plan["overall_risk"] == "high"
        assert len(plan["decisions"]) == 1

    @patch("agents.triage_agent.build_chat_model")
    def test_parse_response_with_valid_data(self, mock_build_chat):
        """Test parsing valid triage response."""
        agent = TriageAgent()
        response = '''{
            "overall_risk": "medium",
            "lanes": ["style"],
            "decisions": [{"file_path": "test.py"}]
        }'''
        
        plan = agent._parse_response(
            response,
            {"priority": "low"},
            []
        )
        
        assert plan["overall_risk"] == "medium"
        assert plan["lanes"] == ["style"]

    @patch("agents.triage_agent.build_chat_model")
    def test_default_lanes_exist(self, mock_build_chat):
        """Test DEFAULT_LANES is defined."""
        assert len(DEFAULT_LANES) > 0
        assert "security" in DEFAULT_LANES
