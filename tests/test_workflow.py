"""Tests for workflow.py - Complete coverage"""
import pytest
from unittest.mock import MagicMock, Mock, patch

from workflow import (
    ReviewState,
    build_review_graph,
    execute_review_workflow,
    _GRAPH_CACHE,
)


class TestBuildReviewGraph:
    """Tests for build_review_graph function."""

    def test_build_review_graph_creates_graph(self):
        """Test graph creation."""
        graph = build_review_graph()
        assert graph is not None

    def test_build_review_graph_caching(self):
        """Test graph is cached."""
        graph1 = build_review_graph()
        graph2 = build_review_graph()
        assert graph1 is graph2

    def test_build_review_graph_has_invoke(self):
        """Test graph has invoke method."""
        graph = build_review_graph()
        assert hasattr(graph, "invoke")


class TestExecuteReviewWorkflow:
    """Tests for execute_review_workflow function."""

    def test_execute_workflow_initial_commit_no_parents(self, mock_supervisor, temp_dir):
        """Test workflow handles commits with no parents."""
        import git
        
        # Create repo with single commit (no parents)
        repo = git.Repo.init(temp_dir)
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello')")
        repo.index.add(["test.py"])
        commit = repo.index.commit("Initial commit")
        
        result = execute_review_workflow(
            mock_supervisor,
            commit,
            ["test.py"],
            "diff",
            progress_callback=None,
        )
        
        assert "review" in result
        assert result["review"]["findings"] == []
        assert result["review"]["commit"] == commit.hexsha

    def test_execute_workflow_with_progress_callback(
        self, mock_supervisor, mock_commit, sample_manifest
    ):
        """Test workflow with progress callback."""
        callback = MagicMock()
        
        mock_supervisor.prepare_file_contexts.return_value = []
        mock_supervisor.run_intake.return_value = sample_manifest
        mock_supervisor.build_context_packets.return_value = []
        mock_supervisor.run_triage.return_value = {"lanes": [], "overall_risk": "low"}
        mock_supervisor.plan_tasks.return_value = []
        mock_supervisor.synthesize_findings.return_value = {
            "normalized_findings": [],
            "summary": "Test",
        }
        mock_supervisor.critique.return_value = {
            "executive_summary": "Summary",
            "grouped_comments": [],
            "follow_ups": [],
        }
        mock_supervisor.record_memory.return_value = None
        
        result = execute_review_workflow(
            mock_supervisor,
            mock_commit,
            ["test.py"],
            "diff",
            progress_callback=callback,
        )
        
        # Callback should be called for node events
        assert callback.call_count > 0

    def test_execute_workflow_with_tasks(
        self, mock_supervisor, mock_commit, sample_manifest, sample_planner_task
    ):
        """Test workflow with tasks."""
        mock_supervisor.prepare_file_contexts.return_value = []
        mock_supervisor.run_intake.return_value = sample_manifest
        mock_supervisor.build_context_packets.return_value = []
        mock_supervisor.run_triage.return_value = {"lanes": ["lint"]}
        mock_supervisor.plan_tasks.return_value = [sample_planner_task]
        mock_supervisor.run_task.return_value = {
            "task_id": "task-1",
            "findings": []
        }
        mock_supervisor.synthesize_findings.return_value = {
            "normalized_findings": [],
            "summary": "Test",
        }
        mock_supervisor.critique.return_value = {
            "executive_summary": "Summary",
            "grouped_comments": [],
            "follow_ups": [],
        }
        mock_supervisor.record_memory.return_value = None
        
        result = execute_review_workflow(
            mock_supervisor,
            mock_commit,
            ["test.py"],
            "diff",
        )
        
        assert "tasks" in result
        assert len(result["tasks"]) == 1

    def test_execute_workflow_error_handling(self, mock_supervisor, mock_commit):
        """Test workflow error handling."""
        mock_supervisor.prepare_file_contexts.side_effect = Exception("Test error")
        
        with pytest.raises(Exception, match="Test error"):
            execute_review_workflow(
                mock_supervisor,
                mock_commit,
                ["test.py"],
                "diff",
            )

    def test_execute_workflow_tracer_integration(
        self, mock_supervisor, mock_commit, sample_manifest
    ):
        """Test workflow integrates with tracer."""
        mock_supervisor.prepare_file_contexts.return_value = []
        mock_supervisor.run_intake.return_value = sample_manifest
        mock_supervisor.build_context_packets.return_value = []
        mock_supervisor.run_triage.return_value = {"lanes": []}
        mock_supervisor.plan_tasks.return_value = []
        mock_supervisor.synthesize_findings.return_value = {
            "normalized_findings": [],
            "summary": "Test",
        }
        mock_supervisor.critique.return_value = {
            "executive_summary": "Summary",
            "grouped_comments": [],
            "follow_ups": [],
        }
        mock_supervisor.record_memory.return_value = None
        
        execute_review_workflow(
            mock_supervisor,
            mock_commit,
            ["test.py"],
            "diff",
        )
        
        # Verify tracer was called
        mock_supervisor.tracer.start_run.assert_called()
        mock_supervisor.tracer.end_run.assert_called()

    def test_execute_workflow_with_parent_run(
        self, mock_supervisor, mock_commit, sample_manifest
    ):
        """Test workflow with parent run."""
        mock_supervisor.prepare_file_contexts.return_value = []
        mock_supervisor.run_intake.return_value = sample_manifest
        mock_supervisor.build_context_packets.return_value = []
        mock_supervisor.run_triage.return_value = {"lanes": []}
        mock_supervisor.plan_tasks.return_value = []
        mock_supervisor.synthesize_findings.return_value = {
            "normalized_findings": [],
            "summary": "Test",
        }
        mock_supervisor.critique.return_value = {
            "executive_summary": "Summary",
            "grouped_comments": [],
            "follow_ups": [],
        }
        mock_supervisor.record_memory.return_value = None
        
        parent_run = "parent-run-id"
        execute_review_workflow(
            mock_supervisor,
            mock_commit,
            ["test.py"],
            "diff",
            parent_run=parent_run,
        )
        
        # Verify parent_run was passed
        call_kwargs = mock_supervisor.tracer.start_run.call_args[1]
        assert call_kwargs.get("parent_run") == parent_run

    def test_execute_workflow_returns_correct_structure(
        self, mock_supervisor, mock_commit, sample_manifest
    ):
        """Test workflow returns correct structure."""
        mock_supervisor.prepare_file_contexts.return_value = []
        mock_supervisor.run_intake.return_value = sample_manifest
        mock_supervisor.build_context_packets.return_value = []
        mock_supervisor.run_triage.return_value = {"lanes": []}
        mock_supervisor.plan_tasks.return_value = []
        mock_supervisor.synthesize_findings.return_value = {
            "normalized_findings": [],
            "summary": "Test",
        }
        mock_supervisor.critique.return_value = {
            "executive_summary": "Summary",
            "grouped_comments": [],
            "follow_ups": [],
        }
        mock_supervisor.record_memory.return_value = None
        
        result = execute_review_workflow(
            mock_supervisor,
            mock_commit,
            ["test.py"],
            "diff",
        )
        
        # Verify result structure
        assert "review" in result
        assert "manifest" in result
        assert "tasks" in result
        assert "task_reports" in result
        assert "node_outputs" in result
