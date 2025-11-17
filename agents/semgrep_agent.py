from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class SemgrepAgent(LLMRepoAgent):
    name = "semgrep"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Semgrep security/pattern scans.",
            checklist=[
                "Prioritize high-signal Semgrep findings.",
                "Annotate false positives when evidence is weak.",
                "Map Semgrep rules to project best practices.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        if not self.tool_available("semgrep"):
            return [self.missing_tool_signal("semgrep", severity="warning")]
        signal = self.run_tool(
            ["semgrep", "scan", "--config", "auto"],
            tool_name="semgrep",
            severity="high",
            description="Semgrep detected potential security issues.",
        )
        return [signal] if signal else []
