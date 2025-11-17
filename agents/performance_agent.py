from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent


class PerformanceAgent(LLMRepoAgent):
    name = "performance"

    def __init__(self, repo_path: Path):
        super().__init__(
            repo_path=repo_path,
            name=self.name,
            specialty="Pytest-benchmark regressions and performance health.",
            checklist=[
                "Indicate whether benchmarks ran or were skipped.",
                "Summarize critical performance regressions.",
                "Call out missing pytest-benchmark plugin if absent.",
            ],
        )

    def collect_signals(self, _) -> List[Dict[str, Any]]:
        if not self.tool_available("pytest"):
            return [self.missing_tool_signal("pytest-benchmark", message="pytest is not installed.")]
        signal = self.run_tool(
            ["pytest", "--benchmark-only", "--benchmark-disable-gc"],
            tool_name="pytest-benchmark",
            severity="info",
            description="pytest-benchmark run failed or reported regressions.",
        )
        return [signal] if signal else []
