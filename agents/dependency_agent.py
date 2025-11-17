from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class DependencyAgent(LLMRepoAgent):
    name = "dependencies"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Dependency vulnerabilities and licensing concerns.",
            checklist=[
                "Surface high-risk CVEs from pip-audit output.",
                "Highlight incompatible or missing licenses.",
                "Suggest remediation steps (upgrade/pin/removal).",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        if not self.tool_available("pip-audit"):
            signals.append(self.missing_tool_signal("pip-audit", severity="warning"))
        else:
            signal = self.run_tool(
                ["pip-audit"],
                tool_name="pip-audit",
                severity="high",
                description="Dependency vulnerabilities detected by pip-audit.",
            )
            if signal:
                signals.append(signal)

        if not self.tool_available("pip-licenses"):
            signals.append(self.missing_tool_signal("pip-licenses"))
        else:
            signal = self.run_tool(
                ["pip-licenses", "--format=plain"],
                tool_name="pip-licenses",
                severity="info",
                description="Review dependency licenses listed by pip-licenses.",
            )
            if signal:
                signals.append(signal)
        return signals
