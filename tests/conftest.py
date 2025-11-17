"""Shared pytest fixtures for all tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock

import git
import pytest


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up environment variables for tests."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGSMITH_TRACING_V2", "0")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_repo(temp_dir):
    """Create a mock git repository."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()
    
    # Initialize git repo
    repo = git.Repo.init(repo_path)
    
    # Create initial commit
    test_file = repo_path / "test.py"
    test_file.write_text("def hello():\n    return 'world'\n")
    repo.index.add(["test.py"])
    repo.index.commit("Initial commit")
    
    return repo


@pytest.fixture
def mock_commit(mock_repo):
    """Create a mock commit with changes."""
    repo = mock_repo
    test_file = Path(repo.working_dir) / "test.py"
    test_file.write_text("def hello():\n    return 'world updated'\n")
    repo.index.add(["test.py"])
    commit = repo.index.commit("Update test file")
    return commit


@pytest.fixture
def mock_llm():
    """Mock LLM chat model."""
    mock = MagicMock()
    mock.invoke.return_value = Mock(content='{"status": "ok"}')
    return mock


@pytest.fixture
def mock_supervisor():
    """Mock Supervisor instance."""
    supervisor = MagicMock()
    supervisor.repo_reference = "test/repo"
    supervisor.repo_path = Path("/tmp/test")
    supervisor.languages = ["python"]
    supervisor.tool_specs = {}
    supervisor.tool_instances = []
    
    # Mock tracer
    supervisor.tracer = MagicMock()
    supervisor.tracer.start_run.return_value = "test-run-id"
    supervisor.tracer.end_run.return_value = None
    
    return supervisor


@pytest.fixture
def sample_manifest() -> Dict[str, Any]:
    """Sample review manifest."""
    return {
        "summary": "Test commit",
        "files": ["test.py"],
        "languages": ["python"],
        "size": "small",
        "priority": "medium",
    }


@pytest.fixture
def sample_planner_task() -> Dict[str, Any]:
    """Sample planner task."""
    return {
        "id": "task-1",
        "title": "Check code quality",
        "specialist": "lint",
        "priority": "high",
        "budget": "m",
        "files": ["test.py"],
        "tool_ids": ["python_lint"],
    }


@pytest.fixture
def sample_finding() -> Dict[str, Any]:
    """Sample finding."""
    return {
        "agent": "lint",
        "file_path": "test.py",
        "span": "10-12",
        "severity": "medium",
        "category": "style",
        "message": "Line too long",
        "recommended_fix": "Break line into multiple lines",
    }


@pytest.fixture
def sample_task_report(sample_planner_task, sample_finding) -> Dict[str, Any]:
    """Sample task report."""
    return {
        "task_id": sample_planner_task["id"],
        "title": sample_planner_task["title"],
        "tool_ids": sample_planner_task["tool_ids"],
        "findings": [sample_finding],
    }


@pytest.fixture
def mock_retriever():
    """Mock repository retriever."""
    retriever = MagicMock()
    retriever.search.return_value = [
        {"content": "Sample code", "metadata": {"file": "test.py"}}
    ]
    retriever.search_code.return_value = []
    retriever.search_documentation.return_value = []
    retriever.search_best_practices.return_value = []
    return retriever


@pytest.fixture
def mock_tracer():
    """Mock LangSmith tracer."""
    tracer = MagicMock()
    tracer.start_run.return_value = "run-id"
    tracer.end_run.return_value = None
    return tracer


@pytest.fixture
def sample_diff():
    """Sample git diff."""
    return """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
 def hello():
-    return 'world'
+    return 'world updated'
"""


@pytest.fixture
def sample_patch():
    """Sample patch text."""
    return """@@ -1,2 +1,2 @@
 def hello():
-    return 'world'
+    return 'world updated'
"""


@pytest.fixture
def mock_file_context():
    """Mock file context."""
    return {
        "file_path": "test.py",
        "patch": "+ return 'world updated'",
        "old_content": "def hello():\n    return 'world'\n",
        "new_content": "def hello():\n    return 'world updated'\n",
    }


@pytest.fixture
def mock_chroma_collection():
    """Mock Chroma collection."""
    collection = MagicMock()
    collection.add.return_value = None
    collection.query.return_value = {
        "documents": [["Sample code"]],
        "metadatas": [[{"file": "test.py"}]],
        "distances": [[0.1]],
    }
    return collection
