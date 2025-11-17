from __future__ import annotations

import ast
import os
import pickle
from pathlib import Path
from typing import Dict, Optional

import networkx as nx

from graph_defination import (
    normalize_repo_reference,
    repo_pickle_name,
    repo_slug,
    should_skip_path,
)

GRAPH_DIR = Path(os.environ.get("LOCAL_GRAPH_DIR", ".local_graphs"))
GRAPH_DIR.mkdir(parents=True, exist_ok=True)


def _module_name_from_path(repo_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(repo_root)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _build_module_index(repo_root: Path) -> Dict[Path, str]:
    module_index: Dict[Path, str] = {}
    for file_path in repo_root.rglob("*.py"):
        if should_skip_path(file_path.parts):
            continue
        module_index[file_path] = _module_name_from_path(repo_root, file_path)
    return module_index


def _resolve_relative_module(current_module: str, module: Optional[str], level: int) -> str:
    parts = current_module.split(".")
    if level > 0:
        base_parts = parts[:-level] if level < len(parts) else []
    else:
        base_parts = parts

    if module:
        module_parts = module.split(".")
        full = base_parts + module_parts
    else:
        full = base_parts

    return ".".join(p for p in full if p)


def build_import_graph(repo_path: str | Path, repo_reference: str) -> nx.DiGraph:
    """
    Build an import graph for the repository.

    Nodes are module names, edges represent import relationships.
    """
    repo_root = Path(repo_path).resolve()
    canonical_repo = normalize_repo_reference(repo_reference)
    slug = repo_slug(canonical_repo)

    module_index = _build_module_index(repo_root)
    module_names = set(module_index.values())

    graph = nx.DiGraph()
    graph.graph["repo_reference"] = canonical_repo
    graph.graph["repo_slug"] = slug

    for path, module_name in module_index.items():
        rel_path = path.relative_to(repo_root).as_posix()
        graph.add_node(
            module_name,
            repo_reference=canonical_repo,
            repo_slug=slug,
            file_path=rel_path,
        )

    for file_path, current_module in module_index.items():
        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            rel = file_path.relative_to(repo_root).as_posix()
            print(f"[graph_store] Skipping {rel}: {exc}")
            continue

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            print(f"[graph_store] Could not parse {file_path}: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    if target in module_names:
                        graph.add_edge(current_module, target, kind="import")
            elif isinstance(node, ast.ImportFrom):
                level = node.level or 0
                if node.module is None:
                    for alias in node.names:
                        target_mod = _resolve_relative_module(current_module, alias.name, level)
                        if target_mod in module_names:
                            graph.add_edge(current_module, target_mod, kind="import_from")
                else:
                    target_mod = _resolve_relative_module(current_module, node.module, level)
                    if target_mod in module_names:
                        graph.add_edge(current_module, target_mod, kind="import_from")

    print(
        f"[graph_store] Built graph for {canonical_repo} with "
        f"{graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges."
    )
    return graph


def _graph_path(repo_reference: str) -> Path:
    slug = repo_pickle_name(repo_reference)
    return GRAPH_DIR / f"{slug}.pkl"


def save_graph(g: nx.DiGraph, repo_reference: str) -> Path:
    path = _graph_path(repo_reference)
    with path.open("wb") as fh:
        pickle.dump(g, fh)
    print(f"[graph_store] Saved graph to {path}")
    return path


def load_graph(repo_reference: str) -> Optional[nx.DiGraph]:
    path = _graph_path(repo_reference)
    if not path.exists():
        print(f"[graph_store] No graph found at {path}")
        return None
    with path.open("rb") as fh:
        graph = pickle.load(fh)
    return graph
