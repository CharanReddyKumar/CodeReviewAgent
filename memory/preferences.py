from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from graph_defination import normalize_repo_reference, repo_slug

PREFERENCE_ROOT = Path.home() / ".agentic_reviewer" / "preferences"
PREFERENCE_ROOT.mkdir(parents=True, exist_ok=True)

Action = Literal["accepted", "rejected"]


def _preference_path(repo_reference: str) -> Path:
    slug = repo_slug(normalize_repo_reference(repo_reference))
    return PREFERENCE_ROOT / f"{slug}.jsonl"


def record_feedback(
    repo_reference: str,
    *,
    finding_id: str,
    rule_id: str,
    action: Action,
    summary: str,
    note: Optional[str] = None,
    files: Optional[List[str]] = None,
) -> None:
    entry = {
        "finding_id": finding_id,
        "rule_id": rule_id,
        "action": action,
        "summary": summary,
        "note": note,
        "files": files or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path = _preference_path(repo_reference)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def load_history(repo_reference: str) -> List[Dict[str, Any]]:
    path = _preference_path(repo_reference)
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def summarize_patterns(repo_reference: str, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    entries = load_history(repo_reference)
    buckets: Dict[str, Dict[str, Dict[str, Any]]] = {
        "accepted": defaultdict(lambda: {"rule_id": "", "count": 0, "samples": []}),
        "rejected": defaultdict(lambda: {"rule_id": "", "count": 0, "samples": []}),
    }
    for entry in entries:
        action = entry.get("action")
        if action not in buckets:
            continue
        rule_id = entry.get("rule_id") or "unknown"
        bucket = buckets[action][rule_id]
        bucket.setdefault("rule_id", rule_id)
        bucket["count"] += 1
        sample = {
            "summary": entry.get("summary"),
            "note": entry.get("note"),
            "files": entry.get("files", []),
        }
        bucket["samples"].append(sample)
    summarized: Dict[str, List[Dict[str, Any]]] = {"accepted": [], "rejected": []}
    for action, grouped in buckets.items():
        ordered = sorted(grouped.values(), key=lambda item: item["count"], reverse=True)
        for entry in ordered[:limit]:
            summarized[action].append(entry)
    return summarized
