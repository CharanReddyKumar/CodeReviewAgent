from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from agents.supervisor import Supervisor
from agents.executor_agent import ActionExecutor
from agents.review_types import PlannerTask
from telemetry.langsmith import LangSmithTracer


class _TracerStub(LangSmithTracer):
    def __init__(self) -> None:
        pass

    def child_run(self, *_args, **_kwargs):  # type: ignore[override]
        return object()

    def end_run(self, *_args, **_kwargs):  # type: ignore[override]
        return None


class _ExecutorStub(ActionExecutor):
    def __init__(self) -> None:
        pass

    def execute(self, *_args, **_kwargs):  # type: ignore[override]
        return "ok"


def test_run_task_uses_targeted_contexts():
    supervisor: Supervisor = Supervisor.__new__(Supervisor)
    supervisor.tracer = cast(LangSmithTracer, _TracerStub())
    supervisor.executor_agent = cast(ActionExecutor, _ExecutorStub())
    supervisor.tool_instances = {"file_tool": object()}
    supervisor.tool_specs = {"file_tool": SimpleNamespace(scope="file")}
    supervisor._emit_progress = lambda *args, **kwargs: None  # type: ignore[attr-defined]

    contexts = [
        Supervisor.FileReviewContext(
            file_path="focused.py",
            patch_text="+1",
            query="focused",
            context={"structured": {}},
        ),
        Supervisor.FileReviewContext(
            file_path="other.py",
            patch_text="+2",
            query="other",
            context={"structured": {}},
        ),
    ]

    task: PlannerTask = {
        "id": "task-1",
        "title": "Check focused file",
        "tool_ids": ["file_tool"],
        "files": ["focused.py"],
        "actions": [
            {
                "type": "tool",
                "description": "Inspect focused file",
                "files": ["focused.py"],
                "tool_ids": ["file_tool"],
            }
        ],
    }

    commit = SimpleNamespace(hexsha="abc123", summary="test summary")

    captured_contexts = {}

    def _fake_run_file_tool(_self, _tool, scoped_contexts, _tool_id):
        captured_contexts["value"] = scoped_contexts
        return []

    supervisor._run_file_tool = _fake_run_file_tool.__get__(supervisor, Supervisor)  # type: ignore[attr-defined]

    supervisor.run_task(task, contexts, commit, commit_run="run", manifest={})

    assert "value" in captured_contexts
    assert len(captured_contexts["value"]) == 1
    assert captured_contexts["value"][0].file_path == "focused.py"
