from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class LintAgent(LLMRepoAgent):
    name = "lint"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Static lint compliance (ruff).",
            checklist=[
                "Highlight true positives with repro steps.",
                "Group related lint errors when possible.",
                "Suppress noise from auto-generated files.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        if not self.tool_available("ruff"):
            return [self.missing_tool_signal("ruff")]
        signal = self.run_tool(
            ["ruff", "check", "."],
            tool_name="ruff",
            severity="medium",
            description="ruff lint failures detected.",
        )
        return [signal] if signal else []
