from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class SecretsAgent(LLMRepoAgent):
    name = "secrets"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Secret scanning and credential hygiene.",
            checklist=[
                "Escalate confirmed credential leaks.",
                "Differentiate real secrets from test fixtures.",
                "Recommend rotation/removal steps when needed.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        if not self.tool_available("detect-secrets"):
            return [self.missing_tool_signal("detect-secrets", severity="warning")]
        signal = self.run_tool(
            ["detect-secrets", "scan", "--all-files", "--force-use-all-plugins"],
            tool_name="detect-secrets",
            severity="high",
            description="Potential secrets detected by detect-secrets.",
            issue_on=(3,),
            success_codes=(0,),
        )
        if signal:
            return [signal]
        return []
