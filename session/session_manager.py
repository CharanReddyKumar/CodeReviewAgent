from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from graph_defination import normalize_repo_reference, repo_slug

SESSIONS_ROOT = Path.home() / ".agentic_reviewer" / "sessions"
SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_session_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value or "default")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewSessionManager:
    """Persist incremental review metadata for a repo/session combo."""

    def __init__(
        self,
        repo_reference: str,
        branch: str,
        session_id: Optional[str] = None,
        *,
        pr: Optional[int] = None,
    ) -> None:
        self.repo_reference = normalize_repo_reference(repo_reference)
        self.branch = branch
        self.session_id = session_id or branch
        self.pr = pr
        self.path = self._session_path()
        self.state = self._load_state()
        self.state.setdefault("session_id", self.session_id)
        self.state.setdefault("repo_reference", self.repo_reference)
        self.state.setdefault("branch", branch)
        if pr is not None:
            self.state["pr"] = pr

    def _session_path(self) -> Path:
        slug = repo_slug(self.repo_reference)
        safe_id = _safe_session_id(self.session_id)
        return SESSIONS_ROOT / f"{slug}_{safe_id}.json"

    def _load_state(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {
                "session_id": self.session_id,
                "repo_reference": self.repo_reference,
                "branch": self.branch,
                "artifacts": {},
                "indexed_commits": [],
                "commit_records": [],
                "comments": [],
                "accepted_patches": [],
                "rejected_patches": [],
                "triage_history": [],
            }
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        return {
            "session_id": self.session_id,
            "repo_reference": self.repo_reference,
            "branch": self.branch,
            "artifacts": {},
            "indexed_commits": [],
            "commit_records": [],
            "comments": [],
            "accepted_patches": [],
            "rejected_patches": [],
            "triage_history": [],
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # -- artifact + commit tracking -------------------------------------

    def record_artifact(self, name: str, value: Optional[str], *, refreshed: bool) -> None:
        if not value:
            return
        artifacts = self.state.setdefault("artifacts", {})
        artifacts[name] = {
            "value": value,
            "updated_at": _timestamp(),
            "refreshed": bool(refreshed),
        }

    def indexed_commits(self) -> List[str]:
        return list(self.state.get("indexed_commits", []))

    def last_commit_sha(self) -> Optional[str]:
        commits = self.state.get("indexed_commits", [])
        if commits:
            return commits[-1]
        return None

    def is_commit_indexed(self, commit_sha: str) -> bool:
        return commit_sha in set(self.state.get("indexed_commits", []))

    def record_commit(
        self,
        commit_sha: str,
        summary: str,
        *,
        planning_files: List[str],
        triage: Dict[str, Any],
        findings: List[Dict[str, Any]],
        base_commit: Optional[str],
    ) -> None:
        indexed = self.state.setdefault("indexed_commits", [])
        if commit_sha not in indexed:
            indexed.append(commit_sha)
        commit_records = self.state.setdefault("commit_records", [])
        commit_records.append(
            {
                "sha": commit_sha,
                "summary": summary,
                "timestamp": _timestamp(),
                "files": planning_files,
                "base_commit": base_commit,
                "finding_count": len(findings),
                "triage": triage,
            }
        )
        triage_history = self.state.setdefault("triage_history", [])
        triage_history.append({"commit": commit_sha, **triage})

    # -- comments + feedback --------------------------------------------

    def append_comments(self, commit_sha: str, findings: List[Dict[str, Any]]) -> None:
        if not findings:
            return
        comments = self.state.setdefault("comments", [])
        for finding in findings:
            comments.append(
                {
                    "commit": commit_sha,
                    "file_path": finding.get("file_path"),
                    "span": finding.get("span"),
                    "severity": finding.get("severity"),
                    "message": finding.get("message"),
                    "rule_id": finding.get("rule_id"),
                }
            )

    def get_comments(self) -> List[Dict[str, Any]]:
        return list(self.state.get("comments", []))

    def register_patch_feedback(
        self,
        *,
        finding_id: str,
        action: str,
        note: Optional[str] = None,
    ) -> None:
        target = "accepted_patches" if action == "accepted" else "rejected_patches"
        entries = self.state.setdefault(target, [])
        entries.append({"finding_id": finding_id, "note": note, "timestamp": _timestamp()})

    def session_summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.state.get("session_id"),
            "repo_reference": self.repo_reference,
            "branch": self.branch,
            "indexed_commits": self.indexed_commits(),
            "artifacts": self.state.get("artifacts", {}),
            "triage_history": self.state.get("triage_history", []),
            "comments": self.get_comments(),
        }
