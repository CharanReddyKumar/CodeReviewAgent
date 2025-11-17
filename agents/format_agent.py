from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class FormatAgent(LLMRepoAgent):
    name = "format"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Python formatting consistency (black/isort).",
            checklist=[
                "Black-style formatting is preserved.",
                "Imports follow isort ordering.",
                "Surface actionable edits instead of raw tool logs.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        if not self.tool_available("black"):
            signals.append(self.missing_tool_signal("black"))
        else:
            signal = self.run_tool(
                ["black", "--check", "."],
                tool_name="black",
                severity="medium",
                description="Code formatting diverges from black output.",
            )
            if signal:
                signals.append(signal)

        if not self.tool_available("isort"):
            signals.append(self.missing_tool_signal("isort"))
        else:
            signal = self.run_tool(
                ["isort", "--check-only", "."],
                tool_name="isort",
                severity="low",
                description="Import ordering issues reported by isort.",
            )
            if signal:
                signals.append(signal)
        return signals
