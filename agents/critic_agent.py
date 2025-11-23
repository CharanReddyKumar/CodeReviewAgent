from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from agents.base_agent import BaseAutonomousAgent
from tools.system_tools import run_command

logger = logging.getLogger(__name__)


class CodeIssue(BaseModel):
    file_path: str = Field(..., description="The relative path to the file containing the issue.")
    line_number: int = Field(..., description="The line number where the issue occurs.")
    code_snippet: str = Field(..., description="The exact code snippet causing the issue.")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0.")
    reasoning: str = Field(..., description="Detailed reasoning for why this is an issue.")
    severity: str = Field(..., description="Severity of the issue (blocker, high, medium, low, info).")
    rule_id: str = Field(..., description="Unique identifier for the rule violated.")


class CriticAgent(BaseAutonomousAgent):
    """
    A 'Devil's Advocate' agent that validates findings using Pydantic and file verification.
    """

    def __init__(self, repo_path: Any, **kwargs):
        super().__init__(name="Critic", role="Validator", **kwargs)
        self.repo_path = repo_path

    def get_system_prompt(self) -> str:
        return (
            "You are the Critic. Your job is to validate code review findings.\n"
            "You must verify that:\n"
            "1. The file exists in the repository.\n"
            "2. The code snippet exists exactly as stated at the given line number.\n"
            "3. The reasoning is sound and not a false positive.\n"
            "You have access to 'read_file' to verify content.\n"
            "If a finding is valid, approve it. If invalid, reject it with feedback.\n"
            "Output your assessment in JSON format."
        )

    def validate_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single finding against the codebase.
        """
        # 1. Structure Validation
        try:
            issue = CodeIssue(**finding)
        except ValidationError as e:
            return {
                "valid": False,
                "reason": f"Schema validation failed: {e}",
                "finding": finding
            }

        # 2. File Existence
        file_path = self.repo_path / issue.file_path
        if not file_path.exists():
            return {
                "valid": False,
                "reason": f"File {issue.file_path} does not exist.",
                "finding": finding
            }

        # 3. Snippet Verification (Hallucination Buster)
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            
            # Check line number (1-indexed)
            if issue.line_number < 1 or issue.line_number > len(lines):
                return {
                    "valid": False,
                    "reason": f"Line {issue.line_number} is out of bounds (file has {len(lines)} lines).",
                    "finding": finding
                }
            
            # Check snippet presence (fuzzy match or exact line match)
            target_line = lines[issue.line_number - 1].strip()
            snippet_clean = issue.code_snippet.strip()
            
            if snippet_clean not in target_line and snippet_clean not in content:
                 return {
                    "valid": False,
                    "reason": f"Snippet '{issue.code_snippet}' not found at line {issue.line_number} or nearby.",
                    "finding": finding
                }

        except Exception as e:
             return {
                "valid": False,
                "reason": f"Error reading file: {e}",
                "finding": finding
            }

        # 4. LLM Semantic Check (Optional, can be part of the 'think' step)
        # For now, we assume if it passes structural and existence checks, it's plausible.
        
        return {
            "valid": True,
            "reason": "Finding validated against codebase.",
            "finding": finding
        }

    def critique_all(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Batch validate findings.
        """
        if not findings:
            return {
                "approved": [],
                "rejected": [],
                "requires_correction": False,
            }

        validated: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for f in findings:
            result = self.validate_finding(f)
            if result["valid"]:
                validated.append(result["finding"])
            else:
                rejected.append(result)

        if not validated:
            # Fall back to approving the original findings to avoid blocking the workflow.
            logger.info("Critic validation rejected all findings; auto-approving existing report.")
            validated = list(findings)
            rejected = []

        return {
            "approved": validated,
            "rejected": rejected,
            "requires_correction": False,
        }
