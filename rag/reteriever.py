from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import math
import networkx as nx
import re

from best_practices_docs import get_best_practices_doc_collection
from best_practices_store import get_best_practices_collection
from graph_defination import normalize_repo_reference, repo_slug
from knowledge_graph import store as kg_store
from rag.graph_store import load_graph
from rag.vector_store import get_code_collection


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
RISK_HINTS = {
    "security": ("auth", "secret", "token", "crypto", "password", "login", "oauth"),
    "performance": ("perf", "cache", "throughput", "latency", "batch"),
    "tests": ("tests", "pytest", "fixture"),
    "infra": ("deploy", "docker", "terraform"),
}


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [token for token in TOKEN_RE.findall(text.lower()) if token]


def _looks_like_test_path(path: str) -> bool:
    lowered = path.lower()
    return "test" in lowered.split("/") or lowered.startswith("tests/") or "_test" in lowered


@dataclass
class RetrievalChunk:
    text: str
    metadata: Dict[str, Any]
    score: Optional[float]


class _LexicalIndex:
    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = Path(repo_path) if repo_path else None
        self._token_cache: Dict[str, List[str]] = {}
        self._text_cache: Dict[str, str] = {}

    def set_repo_path(self, repo_path: Path) -> None:
        self.repo_path = Path(repo_path)
        self._token_cache.clear()
        self._text_cache.clear()

    def _read_file(self, relative_path: str) -> str:
        if relative_path in self._text_cache:
            return self._text_cache[relative_path]
        if not self.repo_path:
            return ""
        file_path = self.repo_path / relative_path
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        self._text_cache[relative_path] = text
        return text

    def _tokens(self, relative_path: str) -> List[str]:
        if relative_path in self._token_cache:
            return self._token_cache[relative_path]
        tokens = _tokenize(self._read_file(relative_path))
        self._token_cache[relative_path] = tokens
        return tokens

    def rank(self, relative_paths: Sequence[str], query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
        if not query.strip() or not relative_paths:
            return []
        query_terms = _tokenize(query)
        if not query_terms:
            return []
        documents: List[Tuple[str, List[str]]] = []
        for rel in relative_paths:
            tokens = self._tokens(rel)
            if tokens:
                documents.append((rel, tokens))
        if not documents:
            return []

        N = len(documents)
        avgdl = sum(len(tokens) for _, tokens in documents) / max(N, 1)
        doc_freq: Dict[str, int] = {}
        for _, tokens in documents:
            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1

        def _idf(term: str) -> float:
            df = doc_freq.get(term, 0)
            if df == 0:
                return 0.0
            return math.log((N - df + 0.5) / (df + 0.5) + 1.0)

        k1 = 1.5
        b = 0.75
        scores: List[Tuple[str, float]] = []
        for rel_path, tokens in documents:
            token_counts = {}
            for token in tokens:
                token_counts[token] = token_counts.get(token, 0) + 1
            doc_len = len(tokens)
            score = 0.0
            for term in query_terms:
                tf = token_counts.get(term, 0)
                if tf == 0:
                    continue
                idf = _idf(term)
                norm = tf * (k1 + 1)
                denom = tf + k1 * (1 - b + b * (doc_len / max(avgdl, 1e-6)))
                score += idf * (norm / denom)
            if score > 0:
                scores.append((rel_path, score))
        scores.sort(key=lambda item: item[1], reverse=True)

        ranked: List[Dict[str, Any]] = []
        for rel_path, score in scores[:limit]:
            ranked.append(
                {
                    "relative_path": rel_path,
                    "score": score,
                    "snippet": self._build_snippet(rel_path, query_terms),
                    "kind": "lexical",
                }
            )
        return ranked

    def _build_snippet(self, relative_path: str, query_terms: Sequence[str]) -> str:
        if not self.repo_path:
            return ""
        try:
            lines = (self.repo_path / relative_path).read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return ""
        lowered_terms = [term.lower() for term in query_terms if term]
        for line in lines:
            lowered = line.lower()
            if any(term in lowered for term in lowered_terms):
                return line.strip()
        return (lines[0].strip() if lines else "")


class RepositoryRetriever:
    """
    Unified interface for querying code, docs, commit "best practices",
    and the dependency graph for a repository.
    """

    def __init__(self, repo_reference: str, repo_path: Optional[Path] = None):
        self.repo_reference = normalize_repo_reference(repo_reference)
        self.repo_slug = repo_slug(self.repo_reference)
        self.collection = get_code_collection(self.repo_reference)
        self.best_practices_collection = get_best_practices_collection()
        self.policy_doc_collection = get_best_practices_doc_collection()
        self._import_graph: Optional[nx.DiGraph] = None
        self._code_graph: Optional[nx.MultiDiGraph] = None
        self._module_index: Dict[str, str] = {}
        self._symbol_index: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.repo_path = Path(repo_path).resolve() if repo_path else None
        self._lexical = _LexicalIndex(self.repo_path)

    def set_repo_path(self, repo_path: Path) -> None:
        self.repo_path = Path(repo_path)
        self._lexical.set_repo_path(self.repo_path)

    @staticmethod
    def _score_from_distance(distance: Optional[float]) -> Optional[float]:
        if distance is None:
            return None
        return max(0.0, 1.0 - distance)

    def _query_collection(
        self,
        query: str,
        n_results: int,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalChunk]:
        if not query.strip():
            return []
        result = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks: List[RetrievalChunk] = []
        for idx, doc_id in enumerate(ids):
            text = documents[idx]
            metadata = metadatas[idx] or {}
            distance = distances[idx] if idx < len(distances) else None
            chunks.append(
                RetrievalChunk(
                    text=text,
                    metadata=metadata,
                    score=self._score_from_distance(distance),
                )
            )
        return chunks

    # -- basic queries -----------------------------------------------------

    def search_code(self, query: str, *, n_results: int = 5) -> List[RetrievalChunk]:
        return self._query_collection(query, n_results, where={"content_type": "code"})

    def search_documentation(self, query: str, *, n_results: int = 5) -> List[RetrievalChunk]:
        return self._query_collection(query, n_results, where={"content_type": "doc"})

    def search_best_practices(self, query: str, *, n_results: int = 5) -> List[RetrievalChunk]:
        if not query.strip():
            return []
        result = self.best_practices_collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"repo_reference": self.repo_reference},
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks: List[RetrievalChunk] = []
        for idx, doc_id in enumerate(ids):
            chunks.append(
                RetrievalChunk(
                    text=documents[idx],
                    metadata=metadatas[idx] or {},
                    score=self._score_from_distance(distances[idx] if idx < len(distances) else None),
                )
            )
        return chunks

    def search_policy_docs(
        self,
        query: str,
        *,
        n_results: int = 5,
        source: Optional[str] = None,
    ) -> List[RetrievalChunk]:
        if not query.strip():
            return []
        where: Dict[str, Any] = {}
        if source:
            where["source"] = source
        result = self.policy_doc_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where or None,
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks: List[RetrievalChunk] = []
        for idx, doc_id in enumerate(ids):
            chunks.append(
                RetrievalChunk(
                    text=documents[idx],
                    metadata=metadatas[idx] or {},
                    score=self._score_from_distance(distances[idx] if idx < len(distances) else None),
                )
            )
        return chunks

    def import_neighborhood(
        self,
        module_name: str,
        *,
        depth: int = 1,
        max_nodes: int = 200,
    ) -> Optional[nx.DiGraph]:
        graph = self._ensure_import_graph()
        if graph is None or module_name not in graph:
            return None

        nodes = {module_name}
        frontier = {module_name}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(graph.successors(node))
                next_frontier.update(graph.predecessors(node))
            nodes.update(next_frontier)
            frontier = next_frontier
            if len(nodes) >= max_nodes:
                break

        ordered_nodes = list(nodes)
        if len(ordered_nodes) > max_nodes:
            ordered_nodes = ordered_nodes[:max_nodes]
        return graph.subgraph(ordered_nodes).copy()

    # -- structured retrieval ---------------------------------------------

    def build_context_bundle(
        self,
        file_path: str,
        patch_text: str,
        query: str,
        *,
        risk_tags: Optional[Sequence[str]] = None,
        code_limit: int = 5,
        doc_limit: int = 4,
    ) -> Dict[str, Any]:
        rel_path = self._normalize_path(file_path)
        module_name = self._module_name_for_path(rel_path)
        candidate_paths = self._candidate_paths(rel_path)

        scoped_code = self._scoped_semantic_search(query, candidate_paths, content_type="code", limit=code_limit)
        scoped_docs = self._scoped_semantic_search(query, candidate_paths, content_type="doc", limit=doc_limit)
        lexical_hits = self._lexical.rank(list(candidate_paths), query, limit=3)

        symbol_names = self._extract_symbols_from_patch(patch_text)
        symbol_context = self._symbol_context(module_name, symbol_names)
        related_tests = self._related_tests(module_name)

        best_practices = self._filter_by_risk(
            [self._chunk_to_dict(chunk, default_kind="best_practice") for chunk in self.search_best_practices(query, n_results=8)],
            risk_tags,
        )
        policy_docs = self._filter_by_risk(
            [self._chunk_to_dict(chunk, default_kind="policy") for chunk in self.search_policy_docs(query, n_results=8)],
            risk_tags,
        )
        fallback_code = []
        if len(scoped_code) < code_limit:
            fallback_code = [self._chunk_to_dict(chunk) for chunk in self.search_code(query, n_results=code_limit * 2)][
                : code_limit - len(scoped_code)
            ]
        fallback_docs = []
        if len(scoped_docs) < doc_limit:
            fallback_docs = [
                self._chunk_to_dict(chunk)
                for chunk in self.search_documentation(query, n_results=doc_limit * 2)
            ][
                : doc_limit - len(scoped_docs)
            ]

        return {
            "file_path": rel_path,
            "module": module_name,
            "neighbors": sorted(candidate_paths - {rel_path}),
            "scoped_code": scoped_code + fallback_code,
            "scoped_docs": scoped_docs + fallback_docs,
            "symbol_context": symbol_context,
            "related_tests": related_tests,
            "lexical_hits": lexical_hits,
            "best_practices": best_practices,
            "policy_docs": policy_docs,
        }

    def tagged_search(
        self,
        query: str,
        *,
        kinds: Optional[Iterable[str]] = None,
        risk_domains: Optional[Iterable[str]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        chunks = [self._chunk_to_dict(chunk) for chunk in self._query_collection(query, n_results=limit * 4)]
        kinds_set = {kind.lower() for kind in kinds} if kinds else None
        risk_set = {risk.lower() for risk in risk_domains} if risk_domains else None
        filtered: List[Dict[str, Any]] = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            kind = str(metadata.get("kind", metadata.get("content_type", ""))).lower()
            risk = str(metadata.get("risk_domain", "")).lower()
            if kinds_set and kind not in kinds_set:
                continue
            if risk_set and risk not in risk_set:
                continue
            filtered.append(chunk)
        return filtered[:limit] if filtered else chunks[:limit]

    # -- helpers -----------------------------------------------------------

    def _chunk_to_dict(self, chunk: RetrievalChunk, *, default_kind: Optional[str] = None) -> Dict[str, Any]:
        metadata = dict(chunk.metadata or {})
        if default_kind and not metadata.get("kind"):
            metadata["kind"] = default_kind
        return {
            "text": chunk.text,
            "metadata": metadata,
            "score": chunk.score,
        }

    def _scoped_semantic_search(
        self,
        query: str,
        candidate_paths: Set[str],
        *,
        content_type: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        chunks = self._query_collection(query, n_results=limit * 4, where={"content_type": content_type})
        scoped: List[RetrievalChunk] = []
        if candidate_paths:
            for chunk in chunks:
                rel = chunk.metadata.get("relative_path")
                if rel in candidate_paths:
                    scoped.append(chunk)
                    if len(scoped) >= limit:
                        break
        if len(scoped) < limit:
            scoped.extend(chunks[: limit - len(scoped)])
        return [self._chunk_to_dict(chunk) for chunk in scoped[:limit]]

    def _normalize_path(self, file_path: str) -> str:
        path = PurePosixPath(file_path)
        if path.is_absolute() and self.repo_path:
            try:
                path = PurePosixPath(path.relative_to(self.repo_path))
            except Exception:
                pass
        return path.as_posix()

    def _module_name_for_path(self, file_path: str) -> str:
        if file_path in self._module_index:
            return self._module_index[file_path]
        path = PurePosixPath(file_path)
        if path.suffix != ".py":
            return file_path
        module = ".".join(path.with_suffix("").parts)
        return module

    def _candidate_paths(self, file_path: str, depth: int = 1) -> Set[str]:
        graph = self._ensure_import_graph()
        if not graph:
            return {file_path}
        module_name = self._module_name_for_path(file_path)
        if module_name not in graph:
            return {file_path}
        nodes = {module_name}
        frontier = {module_name}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(graph.successors(node))
                next_frontier.update(graph.predecessors(node))
            nodes.update(next_frontier)
            frontier = next_frontier
        paths: Set[str] = {file_path}
        for node in nodes:
            rel = graph.nodes[node].get("file_path")
            if rel:
                paths.add(rel)
        return paths

    def _ensure_import_graph(self) -> Optional[nx.DiGraph]:
        if self._import_graph is None:
            self._import_graph = load_graph(self.repo_reference)
            self._module_index.clear()
            if self._import_graph:
                for node, data in self._import_graph.nodes(data=True):
                    rel = data.get("file_path")
                    if rel:
                        self._module_index[rel] = node
        return self._import_graph

    def _ensure_code_graph(self) -> Optional[nx.MultiDiGraph]:
        if self._code_graph is None:
            self._code_graph = kg_store.load_layer_graph(self.repo_reference, "code")
            self._symbol_index.clear()
            if self._code_graph:
                for node, data in self._code_graph.nodes(data=True):
                    node_type = data.get("type")
                    if node_type in {"function", "async_function", "class"}:
                        module = data.get("module")
                        name = data.get("name")
                        if not module or not name:
                            continue
                        self._symbol_index.setdefault(module, {})[name] = {
                            "qualified_name": data.get("qualified_name"),
                            "summary": data.get("summary", ""),
                            "span": data.get("span"),
                            "docstring": data.get("docstring", ""),
                            "file_path": data.get("file_path"),
                            "kind": node_type,
                        }
        return self._code_graph

    def _extract_symbols_from_patch(self, patch_text: str) -> List[str]:
        symbols: Set[str] = set()
        if not patch_text:
            return []
        for line in patch_text.splitlines():
            line = line.strip()
            if not line or line.startswith("@@"):
                continue
            if line.startswith("+") or line.startswith("-"):
                line = line[1:].strip()
            if line.startswith("def "):
                name = line.split("def ", 1)[1].split("(", 1)[0].strip()
                if name:
                    symbols.add(name)
            elif line.startswith("class "):
                name = line.split("class ", 1)[1].split(":", 1)[0].strip().split("(", 1)[0]
                if name:
                    symbols.add(name)
        return list(symbols)[:5]

    def _symbol_context(self, module_name: str, symbols: Sequence[str]) -> List[Dict[str, Any]]:
        graph = self._ensure_code_graph()
        if not graph or not module_name:
            return []
        module_index = self._symbol_index.get(module_name, {})
        contexts: List[Dict[str, Any]] = []
        targets = symbols or list(module_index.keys())[:3]
        for name in targets:
            entry = module_index.get(name)
            if not entry:
                continue
            contexts.append(
                {
                    "name": name,
                    "qualified_name": entry.get("qualified_name"),
                    "summary": entry.get("summary"),
                    "span": entry.get("span"),
                    "file_path": entry.get("file_path"),
                    "kind": entry.get("kind"),
                }
            )
        return contexts

    def _related_tests(self, module_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        graph = self._ensure_import_graph()
        if not graph or not module_name or module_name not in graph:
            return []
        tests: List[Dict[str, Any]] = []
        for neighbor in graph.predecessors(module_name):
            rel = graph.nodes[neighbor].get("file_path")
            if not rel or not _looks_like_test_path(rel):
                continue
            tests.append({"file_path": rel, "imports": module_name})
            if len(tests) >= limit:
                break
        return tests

    def _filter_by_risk(
        self,
        chunks: List[Dict[str, Any]],
        risk_tags: Optional[Sequence[str]],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not chunks:
            return []
        if not risk_tags:
            return chunks[:limit]
        normalized = {tag.lower() for tag in risk_tags if tag}
        prioritized: List[Dict[str, Any]] = []
        fallback: List[Dict[str, Any]] = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            risk = str(metadata.get("risk_domain", "")).lower()
            if risk and risk in normalized:
                prioritized.append(chunk)
            else:
                fallback.append(chunk)
        ordered = prioritized + fallback
        return ordered[:limit]
