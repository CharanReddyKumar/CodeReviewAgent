"""Tests for agents/review_types.py - Complete coverage"""
import pytest
from agents.review_types import (
    ReviewManifest,
    ContextPacket,
    TriageDecision,
    TriagePlan,
    PlannerTask,
    TaskAction,
    TaskActionResult,
    SpecialistFinding,
    TaskReport,
    SynthesisOutput,
    CriticOutput,
)


class TestTypeDefinitions:
    """Test TypedDict definitions."""

    def test_review_manifest(self):
        """Test ReviewManifest structure."""
        manifest: ReviewManifest = {
            "summary": "Test commit",
            "files": ["test.py"],
            "languages": ["python"],
            "size": "small",
            "priority": "medium",
        }
        assert manifest["summary"] == "Test commit"
        assert "python" in manifest["languages"]

    def test_context_packet(self):
        """Test ContextPacket structure."""
        packet: ContextPacket = {
            "id": "packet-1",
            "file_path": "test.py",
            "module": "test",
            "patch": "diff content",
        }
        assert packet["id"] == "packet-1"

    def test_triage_decision(self):
        """Test TriageDecision structure."""
        decision: TriageDecision = {
            "file_path": "test.py",
            "risk": "medium",
            "file_type": "python",
            "lanes": ["lint", "security"],
        }
        assert decision["risk"] == "medium"

    def test_triage_plan(self):
        """Test TriagePlan structure."""
        plan: TriagePlan = {
            "overall_risk": "high",
            "lanes": ["security", "performance"],
            "decisions": [],
        }
        assert plan["overall_risk"] == "high"

    def test_planner_task(self):
        """Test PlannerTask structure."""
        task: PlannerTask = {
            "id": "task-1",
            "title": "Check security",
            "specialist": "security",
            "files": ["app.py"],
            "priority": "high",
            "budget": "m",
        }
        assert task["specialist"] == "security"

    def test_task_action(self):
        """Test TaskAction structure."""
        action: TaskAction = {
            "type": "tool",
            "description": "Run linter",
            "tool_ids": ["python_lint"],
        }
        assert action["type"] == "tool"

    def test_specialist_finding(self):
        """Test SpecialistFinding structure."""
        finding: SpecialistFinding = {
            "agent": "lint",
            "file_path": "test.py",
            "severity": "medium",
            "category": "style",
            "message": "Line too long",
        }
        assert finding["agent"] == "lint"

    def test_task_report(self):
        """Test TaskReport structure."""
        report: TaskReport = {
            "task_id": "task-1",
            "title": "Lint check",
            "tool_ids": ["lint"],
            "findings": [],
        }
        assert report["task_id"] == "task-1"

    def test_synthesis_output(self):
        """Test SynthesisOutput structure."""
        output: SynthesisOutput = {
            "normalized_findings": [],
            "summary": "No issues found",
        }
        assert output["summary"] == "No issues found"

    def test_critic_output(self):
        """Test CriticOutput structure."""
        output: CriticOutput = {
            "executive_summary": "Code looks good",
            "grouped_comments": [],
            "follow_ups": [],
        }
        assert output["executive_summary"] == "Code looks good"
