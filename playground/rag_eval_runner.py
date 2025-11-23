"""End-to-end sanity check for the local RAG and graph-RAG pipelines.

The script builds a synthetic repository (see `playground/rag_eval_repo`), indexes it
into the Chroma vector store, refreshes the import graph + code knowledge graph,
and exercises semantic + graph-aware queries via `RepositoryRetriever`.

Run this file directly to produce a small evaluation report printed to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge_graph import build_code_structure_graph
from rag.graph_store import build_import_graph, save_graph
from rag.reteriever import RepositoryRetriever
from rag.vector_store import index_repository

DATASET_ROOT = ROOT / "playground" / "rag_eval_repo"
REPO_REFERENCE = "local/rag-eval"


def _score_hits(hits: Sequence[dict], *, expected_path: str) -> float:
    """Return 1.0 if expected path is ranked first, else a discounted score."""

    for idx, chunk in enumerate(hits):
        rel_path = chunk.get("metadata", {}).get("relative_path")
        if rel_path == expected_path:
            # Reciprocal rank metric to keep it simple.
            return 1.0 / (idx + 1)
    return 0.0


def _chunk_to_dict(chunk) -> dict:
    return {
        "text": chunk.text,
        "metadata": dict(chunk.metadata or {}),
        "score": chunk.score,
    }


def ensure_artifacts() -> None:
    print("[rag-eval] Indexing repository into vector store…")
    index_repository(DATASET_ROOT, REPO_REFERENCE)

    print("[rag-eval] Building import graph…")
    graph = build_import_graph(DATASET_ROOT, REPO_REFERENCE)
    save_graph(graph, REPO_REFERENCE)

    print("[rag-eval] Building code knowledge graph…")
    build_code_structure_graph(DATASET_ROOT, REPO_REFERENCE)



def evaluate_queries() -> None:
    retriever = RepositoryRetriever(REPO_REFERENCE, repo_path=DATASET_ROOT)
    retriever.set_repo_path(DATASET_ROOT)

    code_query = "seasonal drift sensor gaps"
    doc_query = "How do you determine risky sensors?"

    code_hits = [_chunk_to_dict(chunk) for chunk in retriever.search_code(code_query, n_results=4)]
    doc_hits = [_chunk_to_dict(chunk) for chunk in retriever.search_documentation(doc_query, n_results=4)]

    bundle = retriever.build_context_bundle(
        file_path="app/service.py",
        patch_text="",
        query=doc_query,
        risk_tags=["performance"],
    )

    code_score = _score_hits(code_hits, expected_path="app/trend_analyzer.py")
    doc_score = _score_hits(doc_hits, expected_path="docs/forecasting.md")

    print("\n[rag-eval] === Semantic Retrieval Results ===")
    for idx, chunk in enumerate(code_hits, start=1):
        rel = chunk["metadata"].get("relative_path")
        print(f"{idx}. {rel} (score={chunk['score']:.3f})")
    print(f"Code MRR vs expected chunk: {code_score:.2f}")

    print("\n[rag-eval] === Documentation Retrieval Results ===")
    for idx, chunk in enumerate(doc_hits, start=1):
        rel = chunk["metadata"].get("relative_path")
        preview = chunk["text"].splitlines()[0][:80]
        print(f"{idx}. {rel} – {preview}")
    print(f"Doc MRR vs expected doc: {doc_score:.2f}")

    print("\n[rag-eval] === Graph Context Bundle ===")
    print(f"Neighbors (import graph): {bundle['neighbors']}")
    print(f"Related tests: {bundle['related_tests']}")
    print("Scoped code chunks:")
    for chunk in bundle["scoped_code"]:
        rel = chunk["metadata"].get("relative_path")
        print(f"  - {rel} (risk={chunk['metadata'].get('risk_domain')})")
    print("Lexical hits:")
    for item in bundle["lexical_hits"]:
        print(f"  - {item['relative_path']} (score={item['score']:.3f}) snippet={item['snippet']}")

    overall = {
        "code_reciprocal_rank": code_score,
        "doc_reciprocal_rank": doc_score,
        "neighbors": bundle["neighbors"],
        "related_tests": bundle["related_tests"],
    }
    print("\n[rag-eval] Summary Metrics:")
    for key, value in overall.items():
        print(f"  {key}: {value}")


def main() -> None:
    if not DATASET_ROOT.exists():
        raise SystemExit(f"Dataset folder {DATASET_ROOT} is missing. Did you commit it?")

    ensure_artifacts()
    evaluate_queries()


if __name__ == "__main__":
    main()
