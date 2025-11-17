from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.review_types import CriticOutput, PlannerTask, ReviewManifest, TaskReport


class ReviewState(TypedDict, total=False):
    changed_files: List[str]
    diff_excerpt: str
    file_contexts: List[Any]
    commit_run: Any
    manifest: ReviewManifest
    triage: Dict[str, Any]
    context_packets: List[Dict[str, Any]]
    tasks: List[PlannerTask]
    task_reports: List[TaskReport]
    synthesis: Dict[str, Any]
    critic_output: CriticOutput
    normalized_findings: List[Dict[str, Any]]
    review: Dict[str, Any]
    node_outputs: Dict[str, Any]
    _supervisor: Any
    _commit: Any
    _progress_callback: Optional[Callable[[str, Dict[str, Any]], None]]


_GRAPH_CACHE: Dict[str, Any] = {}
_GRAPH_VERSION = 2


def build_review_graph():
    key = f"default_v{_GRAPH_VERSION}"
    if key in _GRAPH_CACHE:
        return _GRAPH_CACHE[key]

    builder = StateGraph(ReviewState)

    severity_order = {"blocker": 5, "high": 4, "medium": 3, "low": 2, "info": 1}

    def _compact_tasks(tasks: List[PlannerTask]) -> List[Dict[str, Any]]:
        preview: List[Dict[str, Any]] = []
        for task in tasks or []:
            preview.append(
                {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "specialist": task.get("specialist"),
                    "priority": task.get("priority"),
                    "budget": task.get("budget"),
                    "files": task.get("files", []),
                    "tools": task.get("tool_ids", []),
                    "actions": task.get("actions", []),
                }
            )
        return preview

    def _summarize_reports(reports: List[TaskReport]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for report in reports or []:
            findings = report.get("findings", []) or []
            top_label = ""
            top_score = 0
            sample = ""
            for finding in findings:
                severity = str(finding.get("severity", "info")).lower()
                score = severity_order.get(severity, 0)
                if score >= top_score:
                    top_score = score
                    top_label = severity
                    sample = finding.get("message", sample)
            if not sample:
                for action in report.get("action_results", []) or []:
                    output = action.get("output")
                    if output:
                        sample = output
                        break
            summaries.append(
                {
                    "task_id": report.get("task_id"),
                    "title": report.get("title"),
                    "tools": report.get("tool_ids", []),
                    "findings": len(findings),
                    "top_severity": top_label or "info",
                    "sample": sample[:160] if sample else "",
                }
            )
        return summaries

    def _notify_progress(state: ReviewState, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        callback = state.get("_progress_callback")
        if not callback:
            return
        data = dict(payload or {})
        commit = state.get("_commit")
        if commit is not None:
            data.setdefault("commit", getattr(commit, "hexsha", ""))
        try:
            callback(event, data)
        except Exception:
            pass

    def intake_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "intake"})
        supervisor = state["_supervisor"]
        commit = state["_commit"]
        manifest = supervisor.run_intake(
            getattr(commit, "summary", ""),
            state.get("changed_files", []),
            state.get("diff_excerpt", ""),
            state.get("commit_run"),
        )
        state["manifest"] = manifest
        state.setdefault("node_outputs", {})["intake"] = manifest
        _notify_progress(state, "node_complete", {"node": "intake"})
        return state

    def context_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "context"})
        supervisor = state["_supervisor"]
        manifest = state.get("manifest") or {}
        file_contexts = state.get("file_contexts", [])
        packets = supervisor.build_context_packets(manifest, file_contexts, state.get("commit_run"))
        state["context_packets"] = packets
        state.setdefault("node_outputs", {})["context"] = {"count": len(packets)}
        _notify_progress(state, "node_complete", {"node": "context", "packets": len(packets)})
        return state

    def triage_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "triage"})
        supervisor = state["_supervisor"]
        manifest = state.get("manifest") or {}
        packets = state.get("context_packets") or []
        triage_plan = supervisor.run_triage(
            manifest,
            packets,
            state.get("diff_excerpt", ""),
            state.get("commit_run"),
        )
        state["triage"] = triage_plan
        state.setdefault("node_outputs", {})["triage"] = {"lanes": triage_plan.get("lanes", [])}
        _notify_progress(state, "node_complete", {"node": "triage", "lanes": triage_plan.get("lanes", [])})
        return state

    def planner_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "planner"})
        supervisor = state["_supervisor"]
        manifest = state.get("manifest") or {}
        packets = state.get("context_packets") or []
        triage_plan = state.get("triage", {})
        tasks = supervisor.plan_tasks(manifest, packets, triage_plan, state.get("commit_run"))
        state["tasks"] = tasks
        state.setdefault("node_outputs", {})["planner"] = {"task_count": len(tasks)}
        _notify_progress(state, "node_complete", {"node": "planner", "tasks": len(tasks)})
        if tasks:
            _notify_progress(state, "plan_update", {"tasks": _compact_tasks(tasks)})
        return state

    def tasks_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "tasks"})
        supervisor = state["_supervisor"]
        tasks = state.get("tasks") or []
        file_contexts = state.get("file_contexts") or []
        reports: List[TaskReport] = []
        for task in tasks:
            reports.append(
                supervisor.run_task(
                    task,
                    file_contexts,
                    state["_commit"],
                    state.get("commit_run"),
                    state.get("manifest"),
                )
            )
        state["task_reports"] = reports
        state.setdefault("node_outputs", {})["tasks"] = {"task_count": len(reports)}
        _notify_progress(state, "node_complete", {"node": "tasks", "reports": len(reports)})
        if reports:
            _notify_progress(state, "execution_update", {"reports": _summarize_reports(reports)})
        return state

    def synthesis_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "synthesis"})
        supervisor = state["_supervisor"]
        manifest = state.get("manifest") or {}
        reports = state.get("task_reports", []) or []
        result = supervisor.synthesize_findings(manifest, reports, state.get("commit_run"))
        state["synthesis"] = result
        state["normalized_findings"] = result.get("normalized_findings", [])
        state.setdefault("node_outputs", {})["synthesis"] = {"summary": result.get("summary", "")}
        _notify_progress(state, "node_complete", {"node": "synthesis", "findings": len(state["normalized_findings"])})
        return state

    def critic_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "critic"})
        supervisor = state["_supervisor"]
        commit = state["_commit"]
        diff_excerpt = state.get("diff_excerpt", "")
        findings = state.get("normalized_findings", [])
        critic_output = supervisor.critique(
            getattr(commit, "summary", ""),
            diff_excerpt,
            findings,
            state.get("commit_run"),
        )
        state["critic_output"] = critic_output
        state.setdefault("node_outputs", {})["critic"] = critic_output
        _notify_progress(state, "node_complete", {"node": "critic"})
        groups = []
        for group in critic_output.get("grouped_comments", []) or []:
            groups.append(
                {
                    "file_path": group.get("file_path"),
                    "severity": group.get("severity"),
                    "message": group.get("message"),
                }
            )
        _notify_progress(
            state,
            "reflection_update",
            {
                "executive_summary": critic_output.get("executive_summary", ""),
                "follow_ups": critic_output.get("follow_ups", []),
                "groups": groups,
                "finding_count": len(findings),
            },
        )
        return state

    def memory_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "memory"})
        supervisor = state["_supervisor"]
        commit = state["_commit"]
        normalized = state.get("normalized_findings", [])
        critic_output = state.get("critic_output", {})
        supervisor.record_memory(commit, critic_output.get("executive_summary", ""), normalized)
        state.setdefault("node_outputs", {})["memory"] = {"logged": True}
        _notify_progress(state, "node_complete", {"node": "memory"})
        return state

    def finalize_node(state: ReviewState) -> ReviewState:
        _notify_progress(state, "node_start", {"node": "finalize"})
        commit = state["_commit"]
        review = {
            "commit": commit.hexsha,
            "summary": getattr(commit, "summary", ""),
            "manifest": state.get("manifest", {}),
            "triage": state.get("triage", {}),
            "context_packets": state.get("context_packets", []),
            "tasks": state.get("tasks", []),
            "task_reports": state.get("task_reports", []),
            "findings": state.get("normalized_findings", []),
            "critic": state.get("critic_output", {}),
        }
        state["review"] = review
        state["tool_results"] = review["findings"]
        state.setdefault("node_outputs", {})["finalize"] = {"finding_count": len(review["findings"])}
        _notify_progress(state, "node_complete", {"node": "finalize", "findings": len(review["findings"])})
        return state

    builder.add_node("intake", intake_node)
    builder.add_node("context", context_node)
    builder.add_node("triage", triage_node)
    builder.add_node("planner", planner_node)
    builder.add_node("tasks", tasks_node)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("critic", critic_node)
    builder.add_node("memory", memory_node)
    builder.add_node("finalize", finalize_node)
    builder.set_entry_point("intake")
    builder.add_edge("intake", "context")
    builder.add_edge("context", "triage")
    builder.add_edge("triage", "planner")
    builder.add_edge("planner", "tasks")
    builder.add_edge("tasks", "synthesis")
    builder.add_edge("synthesis", "critic")
    builder.add_edge("critic", "memory")
    builder.add_edge("memory", "finalize")
    builder.add_edge("finalize", END)

    graph = builder.compile()
    _GRAPH_CACHE[key] = graph
    return graph


def execute_review_workflow(
    supervisor,
    commit,
    changed_files: List[str],
    diff_excerpt: str,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    *,
    parent_run: Any = None,
) -> ReviewState:
    graph = build_review_graph()
    file_contexts = supervisor.prepare_file_contexts(commit) if commit.parents else []
    commit_run = supervisor.tracer.start_run(
        name=f"review:{commit.hexsha[:7]}",
        inputs={"commit": commit.hexsha, "summary": getattr(commit, "summary", "")},
        parent_run=parent_run,
    )
    initial_state: ReviewState = {
        "changed_files": changed_files,
        "diff_excerpt": diff_excerpt,
        "file_contexts": file_contexts,
        "commit_run": commit_run,
        "node_outputs": {},
        "_progress_callback": progress_callback,
        "_supervisor": supervisor,
        "_commit": commit,
    }
    if not commit.parents:
        review = {
            "commit": commit.hexsha,
            "summary": getattr(commit, "summary", ""),
            "manifest": {},
            "context_packets": [],
            "tasks": [],
            "task_reports": [],
            "findings": [],
            "critic": {},
        }
        initial_state["review"] = review
        supervisor.tracer.end_run(commit_run, outputs={"review": review})
        return initial_state
    try:
        final_state = graph.invoke(initial_state)
        supervisor.tracer.end_run(commit_run, outputs={"review": final_state.get("review", {})})
        return final_state
    except Exception as exc:
        supervisor.tracer.end_run(commit_run, error=str(exc))
        raise
