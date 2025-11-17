from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class ComplexityAgent(LLMRepoAgent):
    name = "complexity"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Cyclomatic complexity and unused-code detection.",
            checklist=[
                "Surface radon hotspots with actionable advice.",
                "Call out dead code or unused symbols from vulture.",
                "Focus on the files touched by the current commit when possible.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        if not self.tool_available("radon"):
            signals.append(self.missing_tool_signal("radon"))
        else:
            signal = self.run_tool(
                ["radon", "cc", "-s", "-n", "B", "."],
                tool_name="radon",
                severity="medium",
                description="High cyclomatic complexity detected by radon.",
            )
            if signal:
                signals.append(signal)

        if not self.tool_available("vulture"):
            signals.append(self.missing_tool_signal("vulture"))
        else:
            signal = self.run_tool(
                ["vulture", "."],
                tool_name="vulture",
                severity="low",
                description="Potentially unused code detected by vulture.",
            )
            if signal:
                signals.append(signal)
        return signals
