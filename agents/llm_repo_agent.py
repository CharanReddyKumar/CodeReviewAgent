from __future__ import annotations

import logging
import shutil
from typing import Any, Dict, List, Optional, Sequence, Set

from agents.base_agent import BaseAutonomousAgent
from tools.system_tools import run_command

logger = logging.getLogger(__name__)


class LLMRepoAgent(BaseAutonomousAgent):
    """
    Repo-scoped specialist agent that uses a ReAct loop to investigate the repository.
    """

    def __init__(
        self,
        repo_path: Any,
        *,
        name: str,
        specialty: str,
        checklist: Optional[Sequence[str]] = None,
        task_name: Optional[str] = None,
    ):
        super().__init__(name=name, role=specialty)
        self.repo_path = repo_path
        self.specialty = specialty
        self.checklist = list(checklist or [])
        self.findings: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Tool / signal utilities
    # ------------------------------------------------------------------

    def tool_available(self, executable: str) -> bool:
        """Return True when the executable is discoverable on PATH."""

        return bool(shutil.which(executable))

    def missing_tool_signal(
        self,
        tool_name: str,
        *,
        message: Optional[str] = None,
        severity: str = "info",
    ) -> Dict[str, Any]:
        """Standardized finding describing a missing external tool."""

        return {
            "agent": self.name,
            "rule_id": f"{self.name.upper()}_{tool_name.upper()}_MISSING",
            "severity": severity,
            "file_path": "",
            "line": 0,
            "line_end": 0,
            "message": message or f"{tool_name} is not installed or not on PATH.",
            "code_line": "",
            "references": {"tool": tool_name},
        }

    def run_tool(
        self,
        command: Sequence[str],
        *,
        tool_name: str,
        severity: str,
        description: str,
        timeout: Optional[int] = None,
        success_codes: Optional[Sequence[int]] = None,
        issue_on: Optional[Sequence[int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a command and convert failures into structured findings.

        Args:
            command: Command and arguments to execute.
            tool_name: Display name for logging and rule identifiers.
            severity: Severity to apply when the tool surfaces an issue (exit codes in ``issue_on``).
            description: Human readable summary that will be used for actionable findings.
            timeout: Optional timeout passed through to ``run_command``.
            success_codes: Optional explicit set of exit codes that should be considered success. Defaults to ``{0}``.
            issue_on: Optional set of exit codes that represent actionable findings. When provided, other
                non-success exit codes are treated as tool failures rather than actionable evidence.
        """

        cmd_list = list(command)
        allowed_success: Set[int] = set(success_codes if success_codes is not None else (0,))
        actionable_codes: Optional[Set[int]] = set(issue_on) if issue_on is not None else None

        result = run_command(cmd_list, self.repo_path, timeout=timeout)
        if result.returncode in allowed_success:
            logger.debug("%s succeeded: %s", tool_name, " ".join(cmd_list))
            return None

        references: Dict[str, str] = {"command": " ".join(result.command)}
        if result.stdout:
            references["stdout"] = (
                result.stdout[:1000] + "…" if len(result.stdout) > 1000 else result.stdout
            )
        if result.stderr:
            references["stderr"] = (
                result.stderr[:1000] + "…" if len(result.stderr) > 1000 else result.stderr
            )
        if result.error:
            references["error"] = result.error

        first_line = ""
        if result.stdout:
            first_line = result.stdout.splitlines()[0]
        elif result.stderr:
            first_line = result.stderr.splitlines()[0]

        is_actionable = actionable_codes is None or result.returncode in actionable_codes
        message = description if is_actionable else (
            f"{tool_name} failed with exit code {result.returncode}. See references for details."
        )
        severity_label = severity if is_actionable else "info"

        references["exit_code"] = str(result.returncode)

        return {
            "agent": self.name,
            "rule_id": f"{tool_name.upper()}_FAILURE",
            "severity": severity_label,
            "file_path": "",
            "line": 0,
            "line_end": 0,
            "message": message,
            "code_line": first_line,
            "references": references,
        }

    def collect_signals(self, commit) -> List[Dict[str, Any]]:  # pragma: no cover - overridden per agent
        """Subclasses may override to run concrete tooling and emit findings."""

        return []

    def get_system_prompt(self) -> str:
        checklist_text = ""
        if self.checklist:
            checklist_text = "Checklist:\n- " + "\n- ".join(self.checklist)

        return (
            f"You are the {self.name} agent. Specialty: {self.specialty}.\n"
            f"Your goal is to review the code changes and repository state to find issues related to your specialty.\n"
            f"{checklist_text}\n\n"
            "You have access to tools to analyze the code. Use them to gather evidence.\n"
            "When you find an issue, report it using the 'report_finding' tool.\n"
            "If you need to read a file, use 'read_file'.\n"
            "If you need to run a shell command (like grep or a linter), use 'run_command'.\n"
            "When you are done, use the 'finish' action.\n"
            "Always ground your findings in concrete evidence."
        )

    def observe(self, state: Dict[str, Any]) -> str:
        """
        Observe the current state.
        """
        commit = state.get("commit")
        summary = getattr(commit, "summary", "") if commit else "No commit info"
        
        last_result = state.get("last_result")
        last_action = state.get("last_action")
        
        observation = f"Commit Summary: {summary}\n"
        if last_action:
            observation += f"Last Action: {last_action}\n"
        if last_result:
            observation += f"Last Result: {last_result}\n"
            
        return observation

    def act(self, action: Dict[str, Any]) -> Any:
        """
        Override act to handle specific tools if not in self.tools, or delegate.
        """
        action_type = action.get("type")
        
        if action_type == "tool":
            tool_name = action.get("tool")
            args = action.get("args", {})
            
            if tool_name == "run_command":
                cmd = args.get("command")
                if isinstance(cmd, str):
                    cmd = cmd.split()
                return run_command(cmd, self.repo_path)
                
            if tool_name == "report_finding":
                self.findings.append(args)
                return "Finding recorded."
                
        return super().act(action)

    def _normalize_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not signal:
            return None
        normalized = dict(signal)
        normalized.setdefault("agent", self.name)
        normalized.setdefault("rule_id", f"{self.name.upper()}_ISSUE")
        normalized.setdefault("severity", "info")
        normalized.setdefault("file_path", "")
        normalized.setdefault("line", 0)
        normalized.setdefault("line_end", normalized.get("line", 0) or 0)
        normalized.setdefault("code_line", "")
        normalized.setdefault("references", {})
        return normalized

    def review_repo(self, commit) -> List[Dict]:
        """Entry point for repo-scoped tools invoked by the supervisor."""

        self.findings = []
        try:
            signals = self.collect_signals(commit) or []
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            logger.exception("%s collect_signals failed", self.name)
            self.findings.append(
                {
                    "agent": self.name,
                    "rule_id": f"{self.name.upper()}_ERROR",
                    "severity": "info",
                    "file_path": "",
                    "line": 0,
                    "line_end": 0,
                    "message": f"{self.name} tool run failed: {exc}",
                    "code_line": "",
                    "references": {},
                }
            )
            return self.findings

        for signal in signals:
            normalized = self._normalize_signal(signal)
            if normalized:
                self.findings.append(normalized)
        return self.findings
