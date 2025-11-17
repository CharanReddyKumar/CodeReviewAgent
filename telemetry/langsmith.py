from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class _NullRun:
    def __init__(self):
        self.id = None

    def create_child(self, *_, **__):
        return self

    def end(self, *_, **__):
        return None

    def post(self, *_):
        return None


class LangSmithTracer:
    """
    Lightweight helper that streams reviewer activity to LangSmith (if available).

    Set LANGSMITH_API_KEY (and optionally LANGSMITH_PROJECT) to enable tracing.
    """

    def __init__(self):
        self._client = None
        self._RunTree = None
        tags_env = os.environ.get("LANGSMITH_RUN_TAGS") or os.environ.get("LANGCHAIN_TAGS")
        self.default_tags: List[str] = (
            [tag.strip() for tag in tags_env.split(",") if tag.strip()] if tags_env else []
        )
        self.run_name = os.environ.get("LANGSMITH_RUN_NAME")
        self.project_name = (
            os.environ.get("LANGSMITH_PROJECT")
            or os.environ.get("LANGCHAIN_PROJECT")
            or "agentic-reviewer"
        )

        try:
            from langsmith import Client, RunTree  # type: ignore

            self._client = Client()
            self._RunTree = RunTree
            self.enabled = bool(
                os.environ.get("LANGSMITH_API_KEY")
                or os.environ.get("LANGCHAIN_API_KEY")
                or os.environ.get("LANGCHAIN_API_KEY")
                or os.environ.get("LANGCHAIN_TRACING_V2")
            )
        except Exception:
            self.enabled = False

    def start_run(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Optional[Dict[str, Any]] = None,
        parent_run=None,
    ):
        if not self.enabled or self._RunTree is None or self._client is None:
            return _NullRun()
        try:
            if parent_run and not isinstance(parent_run, _NullRun):
                return parent_run.create_child(
                    name=name,
                    run_type=run_type,
                    inputs=inputs or {},
                    tags=self.default_tags or None,
                )
            resolved_name = self.run_name or name
            return self._RunTree(
                name=resolved_name,
                run_type=run_type,
                inputs=inputs or {},
                project_name=self.project_name,
                ls_client=self._client,
                tags=self.default_tags or None,
            )
        except Exception:
            return _NullRun()

    def end_run(self, run, *, outputs: Optional[Dict[str, Any]] = None, error: str | None = None):
        if not self.enabled or run is None or isinstance(run, _NullRun) or self._client is None:
            return
        try:
            run.end(outputs=outputs or {}, error=error)
            run.post(self._client)
        except Exception:
            pass

    def child_run(self, parent_run, name: str, *, run_type: str = "tool", inputs: Optional[Dict[str, Any]] = None):
        return self.start_run(
            name,
            run_type=run_type,
            inputs=inputs,
            parent_run=parent_run,
        )
