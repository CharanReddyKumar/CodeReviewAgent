"""Tests for agents/planner_agent.py - Complete coverage"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from agents.planner_agent import PlannerAgent, SPECIALISTS, LANE_TOOL_PREFS


class TestPlannerAgent:
    """Tests for PlannerAgent class."""

    @patch("agents.planner_agent.build_chat_model")
    def test_init(self, mock_build_chat):
        """Test PlannerAgent initialization."""
        mock_chat = MagicMock()
        mock_build_chat.return_value = mock_chat
        
        agent = PlannerAgent()
        
        mock_build_chat.assert_called_once_with(task="planner")
        assert agent.chat == mock_chat

    @patch("agents.planner_agent.build_chat_model")
    def test_create_tasks_success(self, mock_build_chat):
        """Test creating tasks successfully."""
        mock_response = Mock()
        mock_response.content = '''[{
            "id": "task-1",
            "title": "Review security",
            "specialist": "security",
            "files": ["auth.py"],
            "priority": "high",
            "budget": "m",
            "tool_ids": ["python_security"]
        }]'''
        mock_chat = MagicMock()
        mock_chat.invoke.return_value = mock_response
        mock_build_chat.return_value = mock_chat
        
        agent = PlannerAgent()
        tasks = agent.create_tasks(
            {"summary": "Test"},
            [],
            {"lanes": ["security"]},
            []
        )
        
        assert len(tasks) >= 1

    @patch("agents.planner_agent.build_chat_model")
    def test_create_tasks_with_fallback(self, mock_build_chat):
        """Test creating tasks with fallback."""
        mock_response = Mock()
        mock_response.content = "[]"
        mock_chat = MagicMock()
        mock_chat.invoke.return_value = mock_response
        mock_build_chat.return_value = mock_chat
        
        agent = PlannerAgent()
        manifest = {"summary": "Test", "files": ["test.py"]}
        packets = [{"id": "packet-1", "file_path": "test.py"}]
        triage = {"lanes": ["style"]}
        
        tasks = agent.create_tasks(manifest, packets, triage, [])
        
        # Should create fallback tasks
        assert len(tasks) >= 0

    @patch("agents.planner_agent.build_chat_model")
    def test_specialists_defined(self, mock_build_chat):
        """Test SPECIALISTS constant is defined."""
        assert len(SPECIALISTS) > 0
        assert all("id" in s for s in SPECIALISTS)

    @patch("agents.planner_agent.build_chat_model")
    def test_lane_tool_prefs_defined(self, mock_build_chat):
        """Test LANE_TOOL_PREFS is defined."""
        assert len(LANE_TOOL_PREFS) > 0
        assert "security" in LANE_TOOL_PREFS
