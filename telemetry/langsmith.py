from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any, ClassVar, Dict, List, Optional


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

    _GLOBAL: ClassVar[Optional["LangSmithTracer"]] = None
    _RUN_STACK: ClassVar[ContextVar[tuple]] = ContextVar("langsmith_run_stack", default=())

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
        LangSmithTracer._GLOBAL = self

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
                run = parent_run.create_child(
                    name=name,
                    run_type=run_type,
                    inputs=inputs or {},
                    tags=self.default_tags or None,
                )
            else:
                resolved_name = self.run_name or name
                run = self._RunTree(
                    name=resolved_name,
                    run_type=run_type,
                    inputs=inputs or {},
                    project_name=self.project_name,
                    ls_client=self._client,
                    tags=self.default_tags or None,
                )
            self._push_run(run)
            self._publish(run)
            return run
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
        finally:
            self._pop_run(run)

    def child_run(self, parent_run, name: str, *, run_type: str = "tool", inputs: Optional[Dict[str, Any]] = None):
        return self.start_run(
            name,
            run_type=run_type,
            inputs=inputs,
            parent_run=parent_run,
        )

    def _publish(self, run) -> None:
        if not self.enabled or isinstance(run, _NullRun) or self._client is None:
            return
        try:
            run.post(self._client)
        except Exception:
            pass

    def _push_run(self, run) -> None:
        if run is None or isinstance(run, _NullRun):
            return
        stack = self._RUN_STACK.get()
        self._RUN_STACK.set(stack + (run,))

    def _pop_run(self, run) -> None:
        if run is None or isinstance(run, _NullRun):
            return
        stack = self._RUN_STACK.get()
        if not stack:
            return
        if stack[-1] is run:
            self._RUN_STACK.set(stack[:-1])
            return
        filtered = tuple(r for r in stack if r is not run)
        self._RUN_STACK.set(filtered)

    @classmethod
    def current(cls) -> Optional["LangSmithTracer"]:
        return cls._GLOBAL

    def current_run(self):
        stack = self._RUN_STACK.get()
        if stack:
            return stack[-1]
        return None
