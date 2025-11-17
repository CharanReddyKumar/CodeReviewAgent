from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import git


def checkout_pr(repo_path: Path, pr_number: int) -> str:
    repo = git.Repo(repo_path)
    remote = repo.remotes.origin
    local_ref = f"pr-{pr_number}"
    remote.fetch(refspec=f"pull/{pr_number}/head:{local_ref}")
    repo.git.checkout(local_ref)
    return repo.head.commit.hexsha


def get_changed_files(repo_path: Path, base_ref: Optional[str] = None) -> List[str]:
    repo = git.Repo(repo_path)
    if base_ref:
        diff = repo.git.diff("--name-only", base_ref, "HEAD")
    else:
        try:
            parent = repo.head.commit.parents[0].hexsha
            diff = repo.git.diff("--name-only", parent, "HEAD")
        except IndexError:
            diff = repo.git.diff("--name-only", "--root", "HEAD")
    return [line.strip() for line in diff.splitlines() if line.strip()]


def build_diff_excerpt(repo_path: Path, base_ref: Optional[str] = None, max_chars: int = 4000) -> str:
    repo = git.Repo(repo_path)
    if base_ref:
        raw = repo.git.diff(base_ref, "HEAD")
    else:
        try:
            parent = repo.head.commit.parents[0].hexsha
            raw = repo.git.diff(parent, "HEAD")
        except IndexError:
            raw = repo.git.diff("--root", "HEAD")
    return raw[:max_chars]
