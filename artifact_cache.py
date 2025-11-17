from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import git

from graph_defination import normalize_repo_reference, repo_slug

CACHE_ROOT = Path(".cache") / "artifacts"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)


def _state_path(repo_reference: str) -> Path:
    slug = repo_slug(normalize_repo_reference(repo_reference))
    return CACHE_ROOT / f"{slug}.json"


def _load_state(repo_reference: str) -> dict:
    path = _state_path(repo_reference)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_state(repo_reference: str, state: dict) -> None:
    path = _state_path(repo_reference)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _repo_head_sha(repo_path: Path) -> str:
    repo = git.Repo(repo_path)
    return repo.head.commit.hexsha


def should_refresh_artifact(
    repo_path: Path,
    repo_reference: str,
    key: str,
    *,
    force: bool = False,
) -> Tuple[bool, str]:
    sha = _repo_head_sha(repo_path)
    if force:
        return True, sha
    state = _load_state(repo_reference)
    cached = state.get(key)
    return cached != sha, sha


def mark_artifact_refreshed(repo_reference: str, key: str, sha: str) -> None:
    state = _load_state(repo_reference)
    state[key] = sha
    _save_state(repo_reference, state)
