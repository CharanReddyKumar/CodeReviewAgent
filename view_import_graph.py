import argparse
import pickle
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import networkx as nx

from graph_defination import normalize_repo_reference, repo_slug
from rag.graph_store import load_graph


def _load_graph(arg: str):
    path = Path(arg)
    if path.suffix == ".pkl" and path.exists():
        with path.open("rb") as fh:
            graph = pickle.load(fh)
        repo_label = path.stem
        return graph, repo_label

    repo_reference = normalize_repo_reference(arg)
    graph = load_graph(repo_reference)
    if graph is None:
        raise SystemExit(f"No graph available for {repo_reference}")
    return graph, repo_reference


def _filter_nodes(graph: nx.DiGraph, *, prefix: Optional[str], limit: Optional[int]):
    nodes = [
        node for node in graph.nodes if isinstance(node, str) and (not prefix or node.startswith(prefix))
    ]
    if not nodes:
        return graph.subgraph([])
    nodes = sorted(nodes)
    if limit and len(nodes) > limit:
        nodes = nodes[:limit]
    return graph.subgraph(nodes).copy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize a repository's import graph.")
    parser.add_argument(
        "repo",
        help="Repository reference (url/slug) or path to a saved .pkl graph.",
    )
    parser.add_argument(
        "--prefix",
        help="Only render modules starting with this dotted prefix.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Trim the visualization to the first N nodes (after filtering).",
    )
    parser.add_argument(
        "--output",
        help="Optional PNG output path. Defaults to <repo>_import_graph.png.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Skip interactive display (useful in headless environments).",
    )
    args = parser.parse_args()

    graph, label = _load_graph(args.repo)
    print(
        f"[view_import_graph] Loaded graph for {label} "
        f"({graph.number_of_nodes()} nodes / {graph.number_of_edges()} edges)"
    )

    subgraph = _filter_nodes(graph, prefix=args.prefix, limit=args.limit)
    if subgraph.number_of_nodes() == 0:
        print("[view_import_graph] No nodes match the requested filters.")
        return

    if args.prefix:
        print(
            f"[view_import_graph] Filtered to prefix '{args.prefix}' -> "
            f"{subgraph.number_of_nodes()} nodes"
        )

    slug = repo_slug(label)
    output_path = Path(args.output or f"{slug}_import_graph.png")

    k_value = 0.6 if subgraph.number_of_nodes() < 80 else 0.3
    pos = nx.spring_layout(subgraph, k=k_value, seed=42, iterations=100)

    plt.figure(figsize=(12, 9))
    nx.draw_networkx_nodes(subgraph, pos, node_size=450, alpha=0.9)
    nx.draw_networkx_edges(subgraph, pos, alpha=0.4, arrows=False)
    nx.draw_networkx_labels(subgraph, pos, font_size=8)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    print(f"[view_import_graph] Saved visualization to {output_path}")

    if not args.no_show:
        try:
            plt.show()
        except Exception:
            pass


if __name__ == "__main__":
    main()
