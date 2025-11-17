from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from graph_defination import normalize_repo_reference
from rag.reteriever import RepositoryRetriever


_REGISTERED_PATHS: Dict[str, Path] = {}


@lru_cache(maxsize=8)
def _get_retriever(repo_reference: str) -> RepositoryRetriever:
    canonical = normalize_repo_reference(repo_reference)
    retriever = RepositoryRetriever(canonical, repo_path=_REGISTERED_PATHS.get(canonical))
    return retriever


def register_repo_path(repo_reference: str, repo_path: Path) -> None:
    canonical = normalize_repo_reference(repo_reference)
    resolved = Path(repo_path)
    _REGISTERED_PATHS[canonical] = resolved
    try:
        retriever = _get_retriever(canonical)
        retriever.set_repo_path(resolved)
    except Exception:
        pass


def _chunk_to_dict(chunk) -> Dict[str, Any]:
    return {
        "text": chunk.text,
        "metadata": chunk.metadata,
        "score": chunk.score,
    }


def fetch_code_context(repo_reference: str, query: str, *, n_results: int = 5) -> List[Dict[str, Any]]:
    retriever = _get_retriever(repo_reference)
    return [_chunk_to_dict(chunk) for chunk in retriever.search_code(query, n_results=n_results)]


def fetch_doc_context(repo_reference: str, query: str, *, n_results: int = 5) -> List[Dict[str, Any]]:
    retriever = _get_retriever(repo_reference)
    return [
        _chunk_to_dict(chunk) for chunk in retriever.search_documentation(query, n_results=n_results)
    ]


def fetch_best_practices(repo_reference: str, query: str, *, n_results: int = 5) -> List[Dict[str, Any]]:
    retriever = _get_retriever(repo_reference)
    return [
        _chunk_to_dict(chunk) for chunk in retriever.search_best_practices(query, n_results=n_results)
    ]


def fetch_import_context(
    repo_reference: str,
    module_name: str,
    *,
    depth: int = 1,
) -> Optional[Dict[str, Any]]:
    retriever = _get_retriever(repo_reference)
    subgraph = retriever.import_neighborhood(module_name, depth=depth)
    if subgraph is None:
        return None
    return {
        "nodes": list(subgraph.nodes),
        "edges": [{"source": source, "target": target} for source, target in subgraph.edges],
    }


def build_structured_context(
    repo_reference: str,
    file_path: str,
    patch_text: str,
    query: str,
    *,
    risk_tags: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    retriever = _get_retriever(repo_reference)
    return retriever.build_context_bundle(
        file_path=file_path,
        patch_text=patch_text,
        query=query,
        risk_tags=risk_tags,
    )


def fetch_tagged_context(
    repo_reference: str,
    query: str,
    *,
    kinds: Optional[Sequence[str]] = None,
    risk_domains: Optional[Sequence[str]] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    retriever = _get_retriever(repo_reference)
    return retriever.tagged_search(
        query,
        kinds=kinds,
        risk_domains=risk_domains,
        limit=limit,
    )
