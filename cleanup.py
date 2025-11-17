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


def _is_git_tracked(repo_path: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(repo_path)
    except ValueError:
        return True
    output = _git_ls(repo_path, str(relative))
    return bool(output)


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


def prune_workspace(repo_path: Path, *, patterns: Sequence[str] = DEFAULT_PATTERNS, dry_run: bool = False) -> CleanupReport:
    repo_path = Path(repo_path)
    removed: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []
    for match in _iter_matches(repo_path, patterns):
        if match == repo_path:
            continue
        rel = str(match.relative_to(repo_path))
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
