from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Optional

import networkx as nx

from graph_defination import normalize_repo_reference, repo_slug

GRAPH_ROOT = Path(os.environ.get("KNOWLEDGE_GRAPH_DIR", ".local_graphs"))
GRAPH_ROOT.mkdir(parents=True, exist_ok=True)


def _layer_path(repo_reference: str, layer: str) -> Path:
    slug = repo_slug(normalize_repo_reference(repo_reference))
    return GRAPH_ROOT / f"{slug}_{layer}.pkl"


def _global_path(name: str) -> Path:
    return GRAPH_ROOT / f"{name}.pkl"


def save_layer_graph(graph: nx.Graph, repo_reference: str, layer: str) -> Path:
    path = _layer_path(repo_reference, layer)
    with path.open("wb") as fh:
        pickle.dump(graph, fh)
    return path


def load_layer_graph(repo_reference: str, layer: str) -> Optional[nx.Graph]:
    path = _layer_path(repo_reference, layer)
    if not path.exists():
        return None
    with path.open("rb") as fh:
        return pickle.load(fh)


def save_global_graph(graph: nx.Graph, name: str) -> Path:
    path = _global_path(name)
    with path.open("wb") as fh:
        pickle.dump(graph, fh)
    return path


def load_global_graph(name: str) -> Optional[nx.Graph]:
    path = _global_path(name)
    if not path.exists():
        return None
    with path.open("rb") as fh:
        return pickle.load(fh)
