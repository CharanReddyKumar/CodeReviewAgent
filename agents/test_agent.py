from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class TestAgent(LLMRepoAgent):
    name = "tests"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="pytest regressions and flaky test detection.",
            checklist=[
                "Include failing test names / stack traces.",
                "Note when pytest is unavailable in the environment.",
                "Reference past failures from session memory when relevant.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        if not self.tool_available("pytest"):
            return [self.missing_tool_signal("pytest", message="pytest is not installed.", severity="warning")]
        cmd = ["pytest", "--maxfail=1", "--disable-warnings", "-q"]
        extra = os.environ.get("PYTEST_ADDOPTS")
        if extra:
            cmd.extend(extra.split())
        timeout_seconds = int(os.environ.get("PYTEST_MAX_SECONDS", "900"))
        signal = self.run_tool(
            cmd,
            tool_name="pytest",
            severity="high",
            description="pytest failed. Inspect failing tests/logs.",
            timeout=timeout_seconds,
        )
        return [signal] if signal else []
