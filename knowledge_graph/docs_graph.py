from __future__ import annotations

import re
from typing import List, Set

import networkx as nx

from best_practices_docs import get_best_practices_doc_collection
from .store import load_global_graph, save_global_graph

TOPIC_KEYWORDS = {
    "auth": ["auth", "oauth", "login", "jwt"],
    "secrets": ["secret", "credential", "token"],
    "logging": ["log", "observability", "telemetry"],
    "pii": ["pii", "personal data", "gdpr", "hipaa"],
    "database": ["sql", "database", "orm", "query"],
    "network": ["http", "request", "response", "socket"],
}


def _infer_topics(text: str) -> Set[str]:
    topics: Set[str] = set()
    lowered = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            topics.add(topic)
    return topics


def refresh_policy_graph(source_name: str | None = None) -> nx.DiGraph:
    collection = get_best_practices_doc_collection()
    total = collection.count()
    if total == 0:
        graph = load_global_graph("policy") or nx.DiGraph()
        save_global_graph(graph, "policy")
        return graph
    result = collection.get(
        limit=total,
        include=["metadatas", "documents"],
    )
    graph = load_global_graph("policy") or nx.DiGraph()
    graph.graph["layer"] = "policy"

    doc_ids: List[str] = result.get("ids", []) or []
    documents: List[str] = result.get("documents", []) or []
    metadatas: List[dict] = result.get("metadatas", []) or []

    for doc_id, text, metadata in zip(doc_ids, documents, metadatas):
        if not doc_id:
            continue
        node_id = f"policy::{doc_id}"
        topics = _infer_topics(text or "")
        source = metadata.get("source") if isinstance(metadata, dict) else None
        if source_name and source and source != source_name:
            # Skip docs from other repos when refreshing a specific source.
            continue
        graph.add_node(
            node_id,
            type="policy_document",
            source=source,
            path=metadata.get("path") if isinstance(metadata, dict) else None,
            topics=sorted(topics),
        )
        for topic in topics:
            topic_id = f"topic::{topic}"
            graph.add_node(topic_id, type="topic", name=topic)
            graph.add_edge(node_id, topic_id, kind="applies_to")
        if source:
            src_id = f"policy_source::{source}"
            graph.add_node(src_id, type="policy_source", name=source)
            graph.add_edge(node_id, src_id, kind="originates_from")

    save_global_graph(graph, "policy")
    print(
        f"[knowledge_graph] Policy graph updated with {len(doc_ids)} documents "
        f"(topics: {len({t for node in graph.nodes for t in (graph.nodes[node].get('topics') or [])})})"
    )
    return graph
