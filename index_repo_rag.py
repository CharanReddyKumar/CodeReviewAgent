from pathlib import Path
import sys

from artifact_cache import mark_artifact_refreshed, should_refresh_artifact
from repo_manager import get_or_clone_repo
from rag.vector_store import index_repo_code
from rag.graph_store import build_import_graph, save_graph


def main():
    if len(sys.argv) < 3:
        print("Usage: python index_repo_rag.py <repo_url> <branch>")
        sys.exit(1)

    repo_url = sys.argv[1]
    branch = sys.argv[2]

    # Clone repo
    repo_path: Path = get_or_clone_repo(repo_url, branch)
    print(f"[index_repo_rag] Repo ready at {repo_path}")

    refresh_vectors, current_sha = should_refresh_artifact(
        repo_path, repo_url, "vector_sha", force=False
    )
    if refresh_vectors:
        print("[index_repo_rag] Indexing code into vector DB...")
        index_repo_code(repo_path, repo_url)
        mark_artifact_refreshed(repo_url, "vector_sha", current_sha)
    else:
        print("[index_repo_rag] Skipping vector indexing (cached).")

    refresh_graph, current_sha = should_refresh_artifact(
        repo_path, repo_url, "graph_sha", force=False
    )
    if refresh_graph:
        print("[index_repo_rag] Building import graph...")
        g = build_import_graph(repo_path, repo_url)
        print("[index_repo_rag] Saving graph...")
        save_graph(g, repo_url)
        mark_artifact_refreshed(repo_url, "graph_sha", current_sha)
    else:
        print("[index_repo_rag] Skipping graph build (cached).")

    print("[index_repo_rag] ✅ Completed full RAG indexing.")


if __name__ == "__main__":
    main()
