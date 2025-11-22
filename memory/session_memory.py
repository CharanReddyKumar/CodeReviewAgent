from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict

from graph_defination import normalize_repo_reference, repo_slug

MEMORY_ROOT = Path.home() / ".agentic_reviewer" / "memory"
MEMORY_ROOT.mkdir(parents=True, exist_ok=True)


def _memory_path(repo_reference: str) -> Path:
    slug = repo_slug(normalize_repo_reference(repo_reference))
    return MEMORY_ROOT / f"{slug}.jsonl"


def load_recent(repo_reference: str, limit: int = 5) -> List[Dict]:
    path = _memory_path(repo_reference)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    recent = lines[-limit:]
    entries: List[Dict] = []
    for line in recent:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def append_memory(repo_reference: str, entry: Dict) -> None:
    path = _memory_path(repo_reference)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Add timestamp if missing
    if "timestamp" not in entry:
        from datetime import datetime, timezone
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def store_reflection(repo_reference: str, commit_sha: str, decision: str, reasoning: str) -> None:
    """
    Store a reflection on a decision made during review.
    """
    entry = {
        "type": "reflection",
        "commit": commit_sha,
        "decision": decision,
        "reasoning": reasoning,
    }
    append_memory(repo_reference, entry)

