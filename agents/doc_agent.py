from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class DocAgent(LLMRepoAgent):
    name = "docs"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Docstring coverage and documentation quality.",
            checklist=[
                "Reference pydocstyle violations precisely.",
                "Highlight missing or outdated docstrings.",
                "Point to interrogate coverage gaps.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        if not self.tool_available("pydocstyle"):
            signals.append(self.missing_tool_signal("pydocstyle"))
        else:
            signal = self.run_tool(
                ["pydocstyle", "."],
                tool_name="pydocstyle",
                severity="medium",
                description="pydocstyle errors detected.",
            )
            if signal:
                signals.append(signal)
        if not self.tool_available("interrogate"):
            signals.append(self.missing_tool_signal("interrogate"))
        else:
            signal = self.run_tool(
                ["interrogate", "."],
                tool_name="interrogate",
                severity="low",
                description="Docstring coverage below target per interrogate.",
            )
            if signal:
                signals.append(signal)
        return signals
