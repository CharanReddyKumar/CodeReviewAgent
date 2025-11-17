from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import networkx as nx

from .store import load_layer_graph, save_layer_graph


def record_commit_event(
    repo_reference: str,
    commit_sha: str,
    *,
    summary: str,
    author: Optional[str],
    risk_score: Optional[float] = None,
    files_changed: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> nx.DiGraph:
    graph = load_layer_graph(repo_reference, "history") or nx.DiGraph()
    graph.graph["layer"] = "history"
    node_id = f"commit::{commit_sha}"
    graph.add_node(
        node_id,
        type="commit",
        summary=summary,
        author=author,
        risk_score=risk_score,
        files_changed=files_changed,
        timestamp=datetime.utcnow().isoformat(),
        **(metadata or {}),
    )
    save_layer_graph(graph, repo_reference, "history")
    return graph
