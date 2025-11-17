from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import networkx as nx

from .store import load_layer_graph, save_layer_graph


def _finding_id(commit_sha: str, index: int) -> str:
    return f"finding::{commit_sha}::{index}"


def _evidence_id(commit_sha: str, finding_idx: int, key: str) -> str:
    return f"evidence::{commit_sha}::{finding_idx}::{key}"


def record_findings(
    repo_reference: str,
    commit_sha: str,
    findings: Iterable[Dict[str, Any]],
    *,
    report_path: Optional[Path] = None,
) -> nx.MultiDiGraph:
    graph = load_layer_graph(repo_reference, "findings") or nx.MultiDiGraph()
    graph.graph["layer"] = "findings"
    commit_node = f"commit::{commit_sha}"
    graph.add_node(commit_node, type="commit", report=str(report_path) if report_path else None)

    for idx, finding in enumerate(findings):
        node_id = _finding_id(commit_sha, idx)
        graph.add_node(
            node_id,
            type="finding",
            agent=finding.get("agent"),
            severity=finding.get("severity"),
            file_path=finding.get("file_path") or finding.get("file"),
            line=finding.get("line", 0),
            message=finding.get("message"),
            rule_id=finding.get("rule_id"),
        )
        graph.add_edge(commit_node, node_id, kind="reported")
        references = finding.get("references") or {}
        for ref_key, ref_value in references.items():
            evidence_node = _evidence_id(commit_sha, idx, ref_key)
            graph.add_node(
                evidence_node,
                type="evidence",
                reference_key=ref_key,
                reference_value=ref_value,
            )
            graph.add_edge(node_id, evidence_node, kind="supports")

    save_layer_graph(graph, repo_reference, "findings")
    return graph
