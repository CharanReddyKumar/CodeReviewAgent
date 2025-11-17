from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from agents.review_types import ContextPacket, ReviewManifest
from rag.reteriever import RepositoryRetriever
from tools import rag_tools


def _module_name_from_path(file_path: str) -> str:
    path = PurePosixPath(file_path)
    if not path.suffix:
        return ""
    return ".".join(path.with_suffix("").parts)


class ContextAgent:
    """Builds rich context packets using the repository retriever and graph data."""

    def __init__(self, repo_reference: str, retriever: RepositoryRetriever, repo_path: Optional[Path] = None) -> None:
        self.repo_reference = repo_reference
        self.retriever = retriever
        self.repo_path = repo_path
        self.max_patch_chars = 4000
        self.max_context_chunks = 2
        self.max_chunk_chars = 800

    def build_context_packets(
        self,
        manifest: ReviewManifest,
        file_contexts: List,
    ) -> List[ContextPacket]:
        packets: List[ContextPacket] = []
        components = manifest.get("components", [])
        risks = [tag.lower() for tag in (manifest.get("high_risk_tags", []) or []) if tag]
        for idx, ctx in enumerate(file_contexts):
            module = _module_name_from_path(ctx.file_path)
            rag_query = f"{ctx.file_path} {manifest.get('summary','')}"
            default_context = ctx.context or {}
            structured = default_context.get("structured") or {}
            code_chunks = _filter_by_risk(default_context.get("code") or structured.get("scoped_code"), risks)
            doc_chunks = _filter_by_risk(default_context.get("documentation") or structured.get("scoped_docs"), risks)
            best_practices = _filter_by_risk(default_context.get("best_practices") or structured.get("best_practices"), risks)
            policy_chunks = _filter_by_risk(default_context.get("policy_docs") or structured.get("policy_docs"), risks)
            if not code_chunks:
                code_chunks = rag_tools.fetch_code_context(self.repo_reference, rag_query, n_results=2)
            if not doc_chunks:
                doc_chunks = rag_tools.fetch_doc_context(self.repo_reference, rag_query, n_results=2)
            if not best_practices:
                best_practices = rag_tools.fetch_best_practices(self.repo_reference, rag_query, n_results=2)
            import_context = default_context.get("imports")
            if import_context is None and module:
                import_context = rag_tools.fetch_import_context(self.repo_reference, module, depth=1) or []
            tests = structured.get("related_tests") or default_context.get("tests") or []
            lexical = structured.get("lexical_hits") or default_context.get("lexical") or []
            patch_text = _truncate_text(ctx.patch_text or "", self.max_patch_chars)
            packets.append(
                ContextPacket(
                    id=f"ctx_{idx}",
                    file_path=ctx.file_path,
                    module=module,
                    description=f"Components: {', '.join(components) if components else 'unknown'}",
                    neighbors=list({*components, *risks}),
                    tests=[test.get("file_path", str(test)) for test in tests],
                    configs=[],
                    docs=[],
                    history=[],
                    rag_code=_trim_chunks(code_chunks, self.max_context_chunks, self.max_chunk_chars),
                    rag_docs=_trim_chunks(doc_chunks, self.max_context_chunks, self.max_chunk_chars),
                    rag_best_practices=_trim_chunks(best_practices, self.max_context_chunks, self.max_chunk_chars),
                    rag_policy=_trim_chunks(policy_chunks, self.max_context_chunks, self.max_chunk_chars),
                    import_context=import_context,
                    patch=patch_text,
                    symbol_context=structured.get("symbol_context") or default_context.get("symbol_context", []),
                    lexical_context=lexical[:5],
                    memory_patterns=default_context.get("memory_patterns", []),
                )
            )
        return packets


def _truncate_text(text: str, limit: int) -> str:
    if not text or len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _trim_chunks(chunks: Optional[List[Dict[str, Any]]], limit: int, max_chars: int) -> List[Dict[str, Any]]:
    if not chunks:
        return []
    trimmed: List[Dict[str, Any]] = []
    for chunk in chunks[:limit]:
        text = str(chunk.get("text", ""))
        if len(text) > max_chars:
            new_chunk = dict(chunk)
            new_chunk["text"] = _truncate_text(text, max_chars)
            trimmed.append(new_chunk)
        else:
            trimmed.append(chunk)
    return trimmed


def _filter_by_risk(chunks: Optional[List[Dict[str, Any]]], risks: List[str]) -> List[Dict[str, Any]]:
    if not chunks:
        return []
    if not risks:
        return chunks
    prioritized: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    risk_set = set(risks)
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        risk = str(metadata.get("risk_domain", "")).lower()
        if risk and risk in risk_set:
            prioritized.append(chunk)
        else:
            fallback.append(chunk)
    return prioritized + fallback
