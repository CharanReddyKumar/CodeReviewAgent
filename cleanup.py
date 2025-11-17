from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


DEFAULT_PATTERNS: Sequence[str] = (
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    "build",
    "dist",
    "*.egg-info",
    ".ipynb_checkpoints",
    "Thumbs.db",
    ".DS_Store",
    "npm-debug.log",
)


@dataclass
class CleanupReport:
    removed: List[str]
    skipped: List[str]
    errors: List[str]

    def to_dict(self) -> dict:
        return {"removed": self.removed, "skipped": self.skipped, "errors": self.errors}


def _git_ls(repo_path: Path, relative: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "ls-files", relative],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _find_nested_git_root(repo_path: Path, path: Path) -> Path | None:
    path = Path(path)
    for ancestor in (path, *path.parents):
        if ancestor == repo_path:
            break
        git_dir = ancestor / ".git"
        if git_dir.exists():
            return ancestor
    return None


def _is_git_tracked(repo_path: Path, path: Path) -> bool:
    nested_root = _find_nested_git_root(repo_path, path)
    git_root = nested_root or repo_path
    try:
        relative = path.relative_to(git_root)
    except ValueError:
        return True
    output = _git_ls(git_root, str(relative))
    if output:
        return True
    if nested_root is not None:
        # If the file is not tracked within the nested repository we already
        # checked, there is no need to fall back to the outer repo.
        return False
    return False


def _iter_matches(repo_path: Path, patterns: Iterable[str]) -> List[Path]:
    matches = []
    for pattern in patterns:
        matches.extend(repo_path.rglob(pattern))
    unique: List[Path] = []
    seen = set()
    for match in matches:
        try:
            rel = match.relative_to(repo_path)
        except ValueError:
            continue
        key = str(rel)
        if key in seen:
            continue
        seen.add(key)
        unique.append(match)
    return unique


def _is_inside_git_dir(repo_path: Path, path: Path) -> bool:
    try:
        rel_parts = path.relative_to(repo_path).parts
    except ValueError:
        return False
    return ".git" in rel_parts


def prune_workspace(repo_path: Path, *, patterns: Sequence[str] = DEFAULT_PATTERNS, dry_run: bool = False) -> CleanupReport:
    repo_path = Path(repo_path)
    removed: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []
    for match in _iter_matches(repo_path, patterns):
        if match == repo_path:
            continue
        rel = str(match.relative_to(repo_path))
        if _is_inside_git_dir(repo_path, match):
            skipped.append(rel)
            continue
        if _is_git_tracked(repo_path, match):
            skipped.append(rel)
            continue
        if dry_run:
            removed.append(rel)
            continue
        try:
            if match.is_dir():
                shutil.rmtree(match)
            else:
                match.unlink(missing_ok=True)
            removed.append(rel)
        except Exception as exc:  # pragma: no cover
            errors.append(f"{rel}: {exc}")
    return CleanupReport(removed=removed, skipped=skipped, errors=errors)
