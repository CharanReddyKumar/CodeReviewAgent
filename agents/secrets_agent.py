from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agents.llm_repo_agent import LLMRepoAgent
from tools.system_tools import run_command


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

        command = [
            "detect-secrets",
            "scan",
            "--all-files",
            "--force-use-all-plugins",
        ]
        result = run_command(command, self.repo_path)

        if result.returncode not in {0, 3}:
            references: Dict[str, str] = {"command": " ".join(result.command)}
            if result.stdout:
                references["stdout"] = result.stdout[:500]
            if result.stderr:
                references["stderr"] = result.stderr[:500]
            references["exit_code"] = str(result.returncode)
            return [
                {
                    "agent": self.name,
                    "rule_id": "DETECT_SECRETS_FAILURE",
                    "severity": "info",
                    "file_path": "",
                    "line": 0,
                    "line_end": 0,
                    "message": "detect-secrets failed to run. See references for details.",
                    "code_line": "",
                    "references": references,
                }
            ]

        payload: Dict[str, Any] = {}
        if result.stdout:
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                return [
                    {
                        "agent": self.name,
                        "rule_id": "DETECT_SECRETS_PARSE_ERROR",
                        "severity": "info",
                        "file_path": "",
                        "line": 0,
                        "line_end": 0,
                        "message": "detect-secrets returned malformed JSON output.",
                        "code_line": result.stdout[:120],
                        "references": {"stdout": result.stdout[:500]},
                    }
                ]

        findings: List[Dict[str, Any]] = []
        repo_root = Path(self.repo_path)
        results = payload.get("results") or {}
        for rel_path, matches in results.items():
            file_path = str(rel_path)
            file_lines: List[str] = []
            try:
                file_lines = repo_root.joinpath(rel_path).read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                file_lines = []
            for match in matches or []:
                line_no = int(match.get("line_number") or 0)
                code_line = ""
                if file_lines and 1 <= line_no <= len(file_lines):
                    code_line = file_lines[line_no - 1].strip()
                rule_type = str(match.get("type", "secret")).upper().replace(" ", "_")
                findings.append(
                    {
                        "agent": self.name,
                        "rule_id": f"DETECT_SECRETS_{rule_type}",
                        "severity": "high",
                        "file_path": file_path,
                        "line": line_no,
                        "line_end": line_no,
                        "message": f"{match.get('type', 'Secret')} detected by detect-secrets.",
                        "code_line": code_line,
                        "references": {
                            "hashed_secret": match.get("hashed_secret", ""),
                            "is_verified": str(match.get("is_verified", False)),
                        },
                    }
                )

        return findings
