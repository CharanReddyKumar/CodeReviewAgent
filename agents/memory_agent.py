from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from agents.review_types import SpecialistFinding
from memory import session_memory
from memory import preferences as preference_memory


class MemoryAgent:
    """Persists highlights from the final review into session memory."""

    def record(
        self,
        repo_reference: str,
        commit_sha: str,
        summary: str,
        findings: List[SpecialistFinding],
    ) -> None:
        if not repo_reference:
            return
        payload = {
            "commit": commit_sha,
            "summary": summary,
            "highlights": [finding.get("message", "") for finding in findings[:5]],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        session_memory.append_memory(repo_reference, payload)

    def record_feedback_decision(
        self,
        repo_reference: str,
        finding_id: str,
        rule_id: str,
        action: str,
        summary: str,
        *,
        note: str | None = None,
        files: List[str] | None = None,
    ) -> None:
        normalized_action = action.lower()
        if normalized_action not in {"accepted", "rejected"}:
            return
        preference_memory.record_feedback(
            repo_reference,
            finding_id=finding_id,
            rule_id=rule_id,
            action=normalized_action,  # type: ignore[arg-type]
            summary=summary,
            note=note,
            files=files,
        )
