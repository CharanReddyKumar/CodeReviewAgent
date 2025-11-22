from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

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

    def review_repo(self, commit) -> List[Dict]:
        """
        Compatibility method for the Supervisor to call.
        Starts the agent loop.
        """
        initial_state = {
            "commit": commit,
            "memory": []
        }
        self.run(initial_state)
        return self.findings
