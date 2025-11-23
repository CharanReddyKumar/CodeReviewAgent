#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
AGENT_ENTRYPOINT = WORKSPACE_ROOT / "agentic_revewer.py"
LOG_ROOT = WORKSPACE_ROOT / "logs" / "system_runs"
REPORT_ROOT = WORKSPACE_ROOT / "reports"

GRAPH_RE = re.compile(r"Code graph for .* -> (\d+) nodes / (\d+) edges")
DOC_INGEST_RE = re.compile(r"Ingested (\d+) documents .* into '([^']+)'\.")
POLICY_RE = re.compile(r"Policy graph updated with (\d+) documents \(topics: (\d+)\)")
VECTOR_RE = re.compile(r"\[vector_store] .*?(\d+) code chunks and (\d+) documentation chunks")
REPORT_PATH_RE = re.compile(r"\[agentic_reviewer] JSON report written to (.+\.json)")
FINDINGS_RE = re.compile(r"\[agentic_reviewer] Review complete (\d+) finding")


@dataclass
class Scenario:
    name: str
    repo: Path
    branch: str
    max_commits: int
    refresh_artifacts: bool = False


SCENARIOS: List[Scenario] = [
    Scenario(
        name="vulpy-baseline",
        repo=WORKSPACE_ROOT / "playground" / "vulpy",
        branch="master",
        max_commits=1,
        refresh_artifacts=True,
    ),
    Scenario(
        name="full-system-demo",
        repo=WORKSPACE_ROOT / "playground" / "full_system_demo",
        branch="main",
        max_commits=4,
    ),
]


def _ensure_paths() -> tuple[Path, str]:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = LOG_ROOT / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir, run_id


def _run_scenario(scenario: Scenario, log_dir: Path, run_id: str) -> Dict:
    if not scenario.repo.exists():
        raise FileNotFoundError(f"Scenario repo missing: {scenario.repo}")

    session_id = f"diag-{run_id}-{scenario.name}"

    cmd = [
        "python",
        str(AGENT_ENTRYPOINT),
        str(scenario.repo),
        scenario.branch,
        "--max-commits",
        str(scenario.max_commits),
        "--session",
        session_id,
    ]
    if scenario.refresh_artifacts:
        cmd.append("--refresh-artifacts")

    result = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )

    stdout = result.stdout
    log_path = log_dir / f"{scenario.name}.log"
    log_path.write_text(stdout, encoding="utf-8")

    graph_match = GRAPH_RE.search(stdout)
    graph_nodes = int(graph_match.group(1)) if graph_match else 0
    graph_edges = int(graph_match.group(2)) if graph_match else 0

    doc_ingests = DOC_INGEST_RE.findall(stdout)
    policy_match = POLICY_RE.search(stdout)
    vector_match = VECTOR_RE.search(stdout)

    report_paths = [Path(p.strip()) for p in REPORT_PATH_RE.findall(stdout)]
    finding_lines = [int(value) for value in FINDINGS_RE.findall(stdout)]

    report_summaries = []
    for idx, report_path in enumerate(report_paths):
        resolved = report_path if report_path.is_absolute() else (WORKSPACE_ROOT / report_path)
        payload = json.loads(resolved.read_text())
        normalized = payload.get("synthesis", {}).get("normalized_findings", [])
        agents = Counter(item.get("agent", "unknown") for item in normalized)
        severities = Counter(item.get("severity", "info") for item in normalized)
        report_summaries.append(
            {
                "commit": payload.get("commit"),
                "path": str(resolved),
                "finding_count": len(normalized),
                "agents": agents,
                "severities": severities,
                "lanes": payload.get("triage", {}).get("lanes", []),
            }
        )

    return {
        "scenario": scenario.name,
        "command": " ".join(cmd),
        "log_path": str(log_path),
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "doc_ingests": doc_ingests,
        "policy": policy_match.groups() if policy_match else None,
        "vector_chunks": vector_match.groups() if vector_match else None,
        "reports": report_summaries,
        "finding_lines": finding_lines,
    }


def _write_summary(results: List[Dict], log_dir: Path) -> Path:
    timestamp = log_dir.name
    out_dir = REPORT_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / f"system_validation_{timestamp}.md"

    lines: List[str] = ["# System Validation Summary", ""]
    for result in results:
        lines.append(f"## Scenario: {result['scenario']}")
        lines.append("")
        lines.append(f"- Command: `{result['command']}`")
        lines.append(f"- Log: `{result['log_path']}`")
        lines.append(
            f"- Code graph: {result['graph_nodes']} nodes / {result['graph_edges']} edges"
            if result["graph_nodes"]
            else "- Code graph: n/a"
        )
        if result["doc_ingests"]:
            doc_line = ", ".join(f"{count} doc(s) -> {target}" for count, target in result["doc_ingests"])
            lines.append(f"- Best-practice ingestion: {doc_line}")
        if result["policy"]:
            lines.append(
                f"- Policy graph: {result['policy'][0]} documents across {result['policy'][1]} topics"
            )
        if result["vector_chunks"]:
            lines.append(
                f"- Embedding chunks: {result['vector_chunks'][0]} code / {result['vector_chunks'][1]} docs"
            )
        lines.append("")
        for report in result["reports"]:
            lines.append(f"### Commit {report['commit']}")
            lines.append("")
            lines.append(f"- Findings: {report['finding_count']}")
            if report["lanes"]:
                lanes = ", ".join(report["lanes"])
                lines.append(f"- Lanes: {lanes}")
            if report["agents"]:
                agent_parts = ", ".join(f"{agent}({count})" for agent, count in report["agents"].items())
                lines.append(f"- Agents: {agent_parts}")
            if report["severities"]:
                sev_parts = ", ".join(f"{sev}({count})" for sev, count in report["severities"].items())
                lines.append(f"- Severities: {sev_parts}")
            lines.append(f"- Report: `{report['path']}`")
            lines.append("")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def main() -> None:
    log_dir, run_id = _ensure_paths()
    results: List[Dict] = []
    for scenario in SCENARIOS:
        result = _run_scenario(scenario, log_dir, run_id)
        results.append(result)
    summary_path = _write_summary(results, log_dir)
    print(f"[diagnostic] Summary written to {summary_path}")


if __name__ == "__main__":
    main()
