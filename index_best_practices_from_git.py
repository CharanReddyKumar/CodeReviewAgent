
import sys
from pathlib import Path

from repo_manager import get_or_clone_repo
from best_practices_store import ingest_commits_into_best_practices


def main():
    if len(sys.argv) < 3:
        print("Usage: python index_best_practices_from_git.py <repo_url> <branch>")
        sys.exit(1)

    repo_url = sys.argv[1]
    branch = sys.argv[2]

    repo_path: Path = get_or_clone_repo(repo_url, branch)
    print(f"[indexer] Repo ready at {repo_path}")
    ingest_commits_into_best_practices(repo_path, repo_url)


if __name__ == "__main__":
    main()
