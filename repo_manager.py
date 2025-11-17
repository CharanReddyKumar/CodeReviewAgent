
import os
import git
from pathlib import Path
from urllib.parse import urlparse

# New clean repo storage directory
BASE_REPO_DIR = Path(".local_repos")
BASE_REPO_DIR.mkdir(exist_ok=True, parents=True)


def _slug_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [parsed.netloc] + [p for p in path.split("/") if p]
    return "_".join(parts)


def get_or_clone_repo(repo_url: str, branch: str = "main") -> Path:
    repo_id = _slug_from_url(repo_url)
    repo_path = BASE_REPO_DIR / repo_id

    if repo_path.exists():
        print(f"[repo_manager] Repo already exists locally: {repo_path}")
        repo = git.Repo(repo_path)
        repo.remote().fetch()
    else:
        print(f"[repo_manager] Cloning {repo_url} into {repo_path}")
        repo = git.Repo.clone_from(repo_url, repo_path)

    try:
        repo.git.checkout(branch)
    except Exception as e:
        print(f"[repo_manager] Could not checkout branch {branch}: {e}")

    repo.remote().pull()
    return repo_path

