"""
Shared utilities for repository identifiers and graph/vector metadata.

This module centralizes the normalization logic so that every part of the
pipeline (vector store, graph store, visualization, and agents) speaks the
same language when referring to a repository.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse
from typing import Iterable

# Directories we never want to traverse while indexing/graphing.
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}


def _strip_git_suffix(value: str) -> str:
    if value.endswith(".git"):
        return value[: -len(".git")]
    return value


@lru_cache(maxsize=32)
def normalize_repo_reference(value: str) -> str:
    """
    Convert a git URL/slug into a canonical "<host>/<owner>/<repo>" form.
    """
    value = value.strip()
    if not value:
        raise ValueError("Repository identifier cannot be empty.")

    if value.startswith("git@"):
        host_part, path_part = value.split("@", 1)[1].split(":", 1)
        value = f"{host_part}/{path_part}"

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        path = parsed.path.strip("/")
        value = f"{parsed.netloc}/{path}" if path else parsed.netloc

    value = value.strip("/")
    value = _strip_git_suffix(value)
    return value


def repo_slug(value: str) -> str:
    """
    Safe slug for filesystem paths and Chroma collection metadata.
    """
    normalized = normalize_repo_reference(value)
    slug = normalized.replace("/", "_").replace(":", "_")
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", slug)
    return slug


def chroma_collection_name(value: str) -> str:
    """
    Build a deterministic collection name that obeys Chroma's constraints.
    """
    slug = repo_slug(value)
    name = f"code_chunks_{slug}"
    if not name[0].isalnum():
        name = f"c_{name}"
    if not name[-1].isalnum():
        name = f"{name}0"
    return name[:512]


def repo_pickle_name(value: str) -> str:
    """
    Filename (without extension) used for storing import graphs.
    """
    return repo_slug(value)


def should_skip_path(path_parts: Iterable[str]) -> bool:
    """
    Determine whether any part of the path is in our ignore list.
    """
    return any(part in DEFAULT_EXCLUDE_DIRS for part in path_parts)
