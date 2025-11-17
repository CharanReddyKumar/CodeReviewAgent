from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class TypeAgent(LLMRepoAgent):
    name = "types"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Static typing coverage (pyright/mypy).",
            checklist=[
                "Surface blocking type errors with file + line info.",
                "Explain why the type error matters to functionality.",
                "Suggest targeted fixes (annotation, guard, refactor).",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        if self.tool_available("pyright"):
            signal = self.run_tool(
                ["pyright"],
                tool_name="pyright",
                severity="high",
                description="Static type errors reported by pyright.",
            )
            return [signal] if signal else []
        if self.tool_available("mypy"):
            signal = self.run_tool(
                ["mypy", "."],
                tool_name="mypy",
                severity="high",
                description="Static type errors reported by mypy.",
            )
            return [signal] if signal else []
        return [self.missing_tool_signal("pyright/mypy", message="Neither pyright nor mypy is installed.")]
