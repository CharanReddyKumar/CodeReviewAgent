from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from graph_defination import normalize_repo_reference
from knowledge_graph import store as kg_store
from rag.graph_store import load_graph as load_import_graph

app = FastAPI(title="Graph Visualization", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="graph-viz")


def _graph_nodes_edges(graph) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if graph is None:
        return [], []
    nodes: List[Dict[str, str]] = []
    for node_id, data in graph.nodes(data=True):
        label = data.get("path") or data.get("qualified_name") or str(node_id)
        group = data.get("type") or data.get("kind") or "node"
        nodes.append(
            {
                "id": str(node_id),
                "label": label,
                "group": group,
            }
        )
    edges: List[Dict[str, str]] = []
    if hasattr(graph, "edges"):
        for source, target, edge_data in graph.edges(data=True):
            edges.append(
                {
                    "source": str(source),
                    "target": str(target),
                    "kind": edge_data.get("kind", "relation"),
                }
            )
    return nodes, edges


def _load_graph(repo_reference: str, layer: str):
    canonical = normalize_repo_reference(repo_reference)
    layer = layer.lower()
    if layer == "import":
        return load_import_graph(canonical)
    return kg_store.load_layer_graph(canonical, layer)


@app.get("/graph-data")
def graph_data(repo: str, layer: str = "code") -> Dict[str, List[Dict[str, str]]]:
    graph = _load_graph(repo, layer)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"No graph for {repo} ({layer})")
    nodes, edges = _graph_nodes_edges(graph)
    return {"nodes": nodes, "edges": edges}
