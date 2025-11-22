
import os
from pathlib import Path
from urllib.parse import urlparse

import git
from git.exc import GitCommandError


_CACHE_ROOT = Path(os.environ.get("AGENTIC_CACHE_ROOT", Path.home() / ".agentic_reviewer"))
BASE_REPO_DIR = Path(os.environ.get("AGENTIC_REPO_DIR", _CACHE_ROOT / "repos"))
BASE_REPO_DIR.mkdir(exist_ok=True, parents=True)


def _slug_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [parsed.netloc] + [p for p in path.split("/") if p]
    return "_".join(parts)


def _checkout_branch(repo: git.Repo, branch: str) -> None:
    origin = repo.remotes.origin
    try:
        origin.fetch(branch)
    except GitCommandError as exc:
        raise RuntimeError(f"Branch '{branch}' not found in origin.") from exc

    try:
        repo.git.checkout("-B", branch, f"origin/{branch}")
    except GitCommandError as exc:
        raise RuntimeError(f"Unable to checkout branch '{branch}'.") from exc


def get_or_clone_repo(repo_url: str, branch: str = "main") -> Path:
    repo_id = _slug_from_url(repo_url)
    repo_path = BASE_REPO_DIR / repo_id

    if repo_path.exists():
        print(f"[repo_manager] Repo already exists locally: {repo_path}")
        repo = git.Repo(repo_path)
        repo.remotes.origin.fetch()
    else:
        print(f"[repo_manager] Cloning {repo_url} into {repo_path}")
        repo = git.Repo.clone_from(repo_url, repo_path)

    _checkout_branch(repo, branch)
    return repo_path
