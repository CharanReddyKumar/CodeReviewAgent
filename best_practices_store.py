import os
from pathlib import Path

import chromadb
from chromadb.config import Settings

from graph_defination import normalize_repo_reference, repo_slug

_RISK_HINTS = {
    "security": ("auth", "token", "secret", "crypto", "password", "pii", "oauth"),
    "performance": ("perf", "cache", "latency", "throughput", "optimiz"),
    "tests": ("test", "fixture", "pytest"),
}


def _infer_risk_domain(text: str) -> str:
    lowered = (text or "").lower()
    for domain, hints in _RISK_HINTS.items():
        if any(hint in lowered for hint in hints):
            return domain
    return "general"

# Local vectorstore location
CHROMA_DIR = os.environ.get("LOCAL_VECTOR_DIR", ".local_vectorstore")


def get_best_practices_collection():
    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(allow_reset=False),
    )
    return client.get_or_create_collection(name="best_practices")


def ingest_commits_into_best_practices(repo_path: Path, repo_reference: str):
    """
    Store commit messages as lightweight "best practice" hints.
    """
    import git

    repo = git.Repo(repo_path)
    canonical_repo = normalize_repo_reference(repo_reference)
    slug = repo_slug(canonical_repo)

    col = get_best_practices_collection()

    docs = []
    ids = []
    metas = []

    for commit in repo.iter_commits():
        msg = commit.message.strip()
        if not msg:
            continue

        ids.append(f"{canonical_repo}|{commit.hexsha}")
        docs.append(msg)
        metadata = {
            "repo_reference": canonical_repo,
            "repo_slug": slug,
            "sha": commit.hexsha,
            "author": commit.author.name,
            "timestamp": commit.committed_date,
            "summary": commit.summary,
            "kind": "previous_review",
            "language": "text",
            "risk_domain": _infer_risk_domain(msg),
        }
        metadata["tags"] = f"kind:{metadata['kind']},risk:{metadata['risk_domain']}"
        metas.append(metadata)

    if not docs:
        print("[best_practices] No commit messages found.")
        return

    batch_size = 1000
    total = len(docs)
    print(
        f"[best_practices] Ingesting {total} commit messages in batches of {batch_size}..."
    )

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_docs = docs[start:end]
        batch_ids = ids[start:end]
        batch_metas = metas[start:end]

        col.add(documents=batch_docs, metadatas=batch_metas, ids=batch_ids)
        print(f"[best_practices] Added batch {start}–{end} / {total}")

    print(f"[best_practices] ✅ Finished ingesting {total} commit messages.")
