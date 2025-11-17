from __future__ import annotations

from typing import Dict, List, Optional

import networkx as nx

from graph_defination import normalize_repo_reference
from knowledge_graph.store import load_global_graph, load_layer_graph


class RetrievalAgent:
    """
    Pulls evidence bundles from the knowledge graph layers (code structure + policy + history).
    """

    name = "retrieval"

    def __init__(self, repo_reference: str):
        self.repo_reference = normalize_repo_reference(repo_reference)

    def gather(self, changed_files: List[str], topics: List[str]) -> List[Dict]:
        code_graph = load_layer_graph(self.repo_reference, "code")
        history_graph = load_layer_graph(self.repo_reference, "history")
        policy_graph = load_global_graph("policy")
        bundles: List[Dict] = []

        if code_graph is not None:
            bundles.extend(self._bundle_code_graph(code_graph, changed_files))
        if history_graph is not None:
            bundles.extend(self._bundle_history(history_graph, changed_files))
        if policy_graph is not None and topics:
            bundles.extend(self._bundle_policy(policy_graph, topics))
        return bundles[:10]

    def _bundle_code_graph(self, graph: nx.Graph, changed_files: List[str]) -> List[Dict]:
        bundles: List[Dict] = []
        for file_path in changed_files:
            file_id = f"file::{file_path}"
            if file_id not in graph:
                continue
            symbols = []
            neighbors = []
            for _, target, edge_data in graph.out_edges(file_id, data=True):
                if edge_data.get("kind") == "defines":
                    node = graph.nodes[target]
                    symbols.append(
                        {
                            "name": node.get("qualified_name"),
                            "summary": node.get("summary"),
                            "span": node.get("span"),
                        }
                    )
                else:
                    neighbors.append({"target": target, "kind": edge_data.get("kind")})
            bundles.append(
                {
                    "type": "code_context",
                    "file_path": file_path,
                    "symbols": symbols,
                    "edges": neighbors[:20],
                }
            )
        return bundles

    def _bundle_history(self, graph: nx.Graph, changed_files: List[str]) -> List[Dict]:
        bundles: List[Dict] = []
        latest_commits = sorted(
            (node for node in graph.nodes if node.startswith("commit::")),
            key=lambda nid: graph.nodes[nid].get("timestamp", ""),
            reverse=True,
        )[:5]
        for commit_id in latest_commits:
            data = graph.nodes[commit_id]
            bundles.append(
                {
                    "type": "history",
                    "commit": commit_id.replace("commit::", ""),
                    "summary": data.get("summary"),
                    "risk_score": data.get("risk_score"),
                    "files_changed": data.get("files_changed"),
                }
            )
        return bundles

    def _bundle_policy(self, graph: nx.Graph, topics: List[str]) -> List[Dict]:
        bundles: List[Dict] = []
        topic_nodes = {f"topic::{topic}" for topic in topics}
        for topic_node in topic_nodes:
            if topic_node not in graph:
                continue
            docs = []
            for source, _, edge_data in graph.in_edges(topic_node, data=True):
                if edge_data.get("kind") == "applies_to":
                    node = graph.nodes[source]
                    docs.append(
                        {
                            "document": node.get("path") or node.get("source"),
                            "topics": node.get("topics"),
                        }
                    )
            bundles.append({"type": "policy", "topic": topic_node.replace("topic::", ""), "documents": docs[:5]})
        return bundles
