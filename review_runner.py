from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import git
from git import NULL_TREE

from artifact_cache import mark_artifact_refreshed, should_refresh_artifact
from best_practices_docs import ingest_best_practices_docs
from best_practices_store import ingest_commits_into_best_practices
from agents.supervisor import Supervisor
from git_utils import checkout_pr
from cleanup import prune_workspace
from knowledge_graph import (
    build_code_structure_graph,
    record_commit_event,
    record_findings,
    refresh_policy_graph,
)
from rag.graph_store import build_import_graph, save_graph
from rag.vector_store import index_repo_code
from repo_manager import get_or_clone_repo
from report_writer import write_report
from session import ReviewSessionManager
from telemetry.langsmith import LangSmithTracer
from telemetry.run_logger import log_event, set_session as set_log_session, clear_session as clear_log_session
from workflow import execute_review_workflow


def _is_binary_diff(diff) -> bool:
    blob = diff.b_blob or diff.a_blob
    if blob is None:
        return False
    mime = getattr(blob, "mime_type", None)
    if mime and not mime.startswith("text"):
        return True
    try:
        chunk = blob.data_stream.read(1024)
        return b"\x00" in chunk
    except Exception:
        return False


def _collect_diff_metadata(commit, base_commit=None) -> Tuple[List[str], str]:
    base = base_commit
    if base is None:
        base = commit.parents[0] if commit.parents else NULL_TREE
    diffs = commit.diff(base, create_patch=True)
    changed_files: List[str] = []
    excerpts: List[str] = []
    for diff in diffs:
        if _is_binary_diff(diff):
            continue
        path = diff.b_path or diff.a_path or ""
        if not path:
            continue
        changed_files.append(path)
        if diff.diff:
            text = diff.diff.decode("utf-8", errors="ignore")
            excerpts.append(f"File: {path}\n{text[:800]}")
    return changed_files, "\n\n".join(excerpts)[:4000]


def _ensure_best_practices_docs(repo_reference: str, best_practices_docs: Optional[Path]) -> None:
    if best_practices_docs:
        ingest_best_practices_docs(best_practices_docs, repo_reference)
        refresh_policy_graph(repo_reference)
        return

    default_docs = Path("best_docs_folder")
    if default_docs.exists():
        print(f"[agentic_reviewer] Ingesting best-practice docs from {default_docs}...")
        ingest_best_practices_docs(default_docs, repo_reference)
        refresh_policy_graph(repo_reference)


def run_review(
    repo: str,
    branch: str,
    *,
    max_commits: int = 5,
    refresh_artifacts: bool = False,
    refresh_best_practices: bool = False,
    best_practices_docs: Optional[Path] = None,
    force_artifacts: bool = False,
    pr: Optional[int] = None,
    base: Optional[str] = None,
    reports_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Run the multi-agent review workflow for the given repository and branch.

    Returns a list of result dictionaries (one per commit) containing the review payload
    and the path to the JSON report written on disk.
    """

    def _summarize(values: List[str], *, limit: int = 3) -> str:
        if not values:
            return ""
        if len(values) <= limit:
            return ", ".join(values)
        return ", ".join(values[:limit]) + ", ..."

    def _console_progress(event: str, data: Dict[str, Any]) -> None:
        commit = data.get("commit")
        commit_label = f"[{str(commit)[:7]}] " if commit else ""
        prefix = "[agentic_reviewer]"
        message: Optional[str] = None

        if event == "commit_start":
            summary = data.get("summary", "")
            message = f"{prefix} {commit_label}Starting review: {summary}"
        elif event == "commit_complete":
            findings = data.get("findings")
            label = f"{findings} finding{'s' if findings != 1 else ''}" if findings is not None else ""
            message = f"{prefix} {commit_label}Review complete {label}".rstrip()
        elif event == "file_contexts_start":
            count = data.get("file_count")
            message = f"{prefix} {commit_label}Building file contexts ({count} files)..."
        elif event == "file_contexts_ready":
            contexts = data.get("contexts")
            message = f"{prefix} {commit_label}Ready with {contexts} context packets."
        elif event == "node_start":
            node = data.get("node")
            message = f"{prefix} {commit_label}-> {node} phase"
        elif event == "node_complete":
            node = data.get("node")
            details: List[str] = []
            if "packets" in data:
                details.append(f"packets={data['packets']}")
            if "lanes" in data:
                lanes = data.get("lanes") or []
                details.append(f"lanes={_summarize([str(l) for l in lanes])}")
            if "tasks" in data:
                details.append(f"tasks={data['tasks']}")
            if "reports" in data:
                details.append(f"reports={data['reports']}")
            if "findings" in data:
                details.append(f"findings={data['findings']}")
            detail_text = f" ({', '.join(details)})" if details else ""
            message = f"{prefix} {commit_label}[done] {node} complete{detail_text}"
        elif event == "task_start":
            task = data.get("task")
            title = data.get("title") or ""
            tools = data.get("tools") or []
            files = data.get("files") or []
            tool_text = _summarize([str(t) for t in tools])
            file_text = _summarize([str(f) for f in files])
            message = (
                f"{prefix} {commit_label}Task {task or ''} '{title}' "
                f"(tools: {tool_text or 'all'}, files: {file_text or 'all'})"
            )
        elif event == "task_complete":
            task = data.get("task")
            findings = data.get("findings", 0)
            message = f"{prefix} {commit_label}Task {task or ''} complete with {findings} finding(s)"
        elif event == "task_action":
            task = data.get("task")
            desc = data.get("description") or data.get("type") or "action"
            status = data.get("status")
            detail = ""
            if data.get("output"):
                detail = f": {str(data['output'])[:80]}"
            elif isinstance(data.get("findings"), int):
                detail = f" ({data['findings']} finding{'s' if data['findings'] != 1 else ''})"
            message = f"{prefix} {commit_label}    - Action {task or ''} '{desc}' {status}{detail}"
        elif event == "tool_start":
            tool = data.get("tool")
            scope = data.get("scope") or ""
            task = data.get("task") or ""
            message = f"{prefix} {commit_label}  -> Running {tool} [{scope}] for task {task}"
        elif event == "tool_complete":
            tool = data.get("tool")
            findings = data.get("findings", 0)
            message = f"{prefix} {commit_label}  -> {tool} finished ({findings} finding(s))"
        elif event == "tool_findings":
            tool = data.get("tool")
            total = data.get("total_findings", 0)
            findings = data.get("findings") or []
            sample = ""
            if findings:
                first = findings[0]
                sample = first.get("message") or first.get("recommended_fix") or ""
                sample = sample.strip()
                if sample:
                    sample = f": {sample[:120]}"
            message = f"{prefix} {commit_label}    - {tool} surfaced {total} finding(s){sample}"
        elif event == "plan_update":
            tasks = data.get("tasks") or []
            message = (
                f"{prefix} {commit_label}[plan] {len(tasks)} task(s) prepared"
            )
        elif event == "execution_update":
            reports = data.get("reports") or []
            top = reports[0] if reports else {}
            sample = top.get("sample")
            summary = f"top severity {top.get('top_severity')}" if top else ""
            if sample:
                summary += f" – {sample[:80]}"
            summary = summary.strip()
            message = (
                f"{prefix} {commit_label}[exec] {len(reports)} task report(s) consolidated"
                + (f" ({summary})" if summary else "")
            )
        elif event == "reflection_update":
            summary = data.get("executive_summary") or ""
            followups = len(data.get("follow_ups") or [])
            message = (
                f"{prefix} {commit_label}[reflect] {followups} follow-up(s). "
                f"Summary: {summary[:120]}"
            )

        if message:
            print(message, flush=True)

    progress_sink = progress_callback or _console_progress

    def emit(event: str, payload: Optional[Dict[str, Any]] = None, **data: Any) -> None:
        if not progress_sink:
            return
        body: Dict[str, Any] = {}
        if isinstance(payload, dict):
            body.update(payload)
        if data:
            body.update(data)
        try:
            progress_sink(event, body)
        except Exception:
            pass
        log_payload = dict(body)
        log_payload.setdefault("repo", repo)
        log_payload.setdefault("branch", branch)
        log_event(event, log_payload)

    repo_path = get_or_clone_repo(repo, branch)
    emit("repo_ready", path=str(repo_path))
    print(f"[agentic_reviewer] Repo ready at {repo_path}")

    cleanup_report = prune_workspace(repo_path)
    emit("cleanup", cleanup_report.to_dict())
    if cleanup_report.removed:
        print(
            "[agentic_reviewer] Removed transient artifacts: "
            + ", ".join(cleanup_report.removed[:10])
            + ("..." if len(cleanup_report.removed) > 10 else "")
        )
    if cleanup_report.errors:
        print("[agentic_reviewer] Cleanup errors: " + "; ".join(cleanup_report.errors))

    if pr:
        sha = checkout_pr(repo_path, pr)
        print(f"[agentic_reviewer] Checked out PR #{pr} at {sha}")

    session_identifier = session_id or (f"pr-{pr}" if pr else branch)
    session_manager = ReviewSessionManager(repo, branch, session_identifier, pr=pr)

    refresh_vectors, vec_sha = should_refresh_artifact(
        repo_path,
        repo,
        "vector_sha",
        force=refresh_artifacts or force_artifacts,
    )
    if refresh_vectors:
        print("[agentic_reviewer] Refreshing vector store artifacts...")
        emit("vector_store", status="refreshing")
        index_repo_code(repo_path, repo)
        mark_artifact_refreshed(repo, "vector_sha", vec_sha)
    else:
        print("[agentic_reviewer] Using cached vector embeddings.")
        emit("vector_store", status="cached")
    session_manager.record_artifact("vector_sha", vec_sha, refreshed=refresh_vectors)

    refresh_graph, graph_sha = should_refresh_artifact(
        repo_path,
        repo,
        "graph_sha",
        force=refresh_artifacts or force_artifacts,
    )
    if refresh_graph:
        print("[agentic_reviewer] Refreshing import graph...")
        emit("import_graph", status="refreshing")
        graph = build_import_graph(repo_path, repo)
        save_graph(graph, repo)
        mark_artifact_refreshed(repo, "graph_sha", graph_sha)
    else:
        print("[agentic_reviewer] Using cached import graph.")
        emit("import_graph", status="cached")
    session_manager.record_artifact("graph_sha", graph_sha, refreshed=refresh_graph)

    print("[agentic_reviewer] Building code structure knowledge graph...")
    emit("code_graph", status="building")
    build_code_structure_graph(repo_path, repo)

    _ensure_best_practices_docs(repo, best_practices_docs)

    refresh_bp, bp_sha = should_refresh_artifact(
        repo_path,
        repo,
        "best_practices_sha",
        force=refresh_best_practices,
    )
    if refresh_bp:
        print("[agentic_reviewer] Refreshing best practices store...")
        emit("best_practices", status="refreshing")
        ingest_commits_into_best_practices(
            repo_path,
            repo,
            progress_callback=lambda evt, payload=None: emit(evt, **(payload or {})),
        )
        mark_artifact_refreshed(repo, "best_practices_sha", bp_sha)
    else:
        print("[agentic_reviewer] Using cached best practices store.")
        emit("best_practices", status="cached")
    session_manager.record_artifact("best_practices_sha", bp_sha, refreshed=refresh_bp)

    repository = git.Repo(repo_path)
    commits = list(repository.iter_commits(branch, max_count=max_commits))
    if not commits:
        print("[agentic_reviewer] No commits found to review.")
        emit("no_commits", message="Repository history is empty", branch=branch)
        return []

    ordered_commits = list(reversed(commits))
    indexed_commits = set(session_manager.indexed_commits())
    pending_commits = [commit for commit in ordered_commits if commit.hexsha not in indexed_commits]
    if not pending_commits:
        latest_commit = ordered_commits[-1]
        print(
            "[agentic_reviewer] Session is up to date; re-reviewing latest commit "
            f"{latest_commit.hexsha[:7]} for visibility."
        )
        emit(
            "no_commits",
            commit=latest_commit.hexsha,
            summary=latest_commit.summary,
            message="No new commits; re-running latest to keep UI populated.",
        )
        pending_commits = [latest_commit]

    commits = pending_commits

    tracer = LangSmithTracer()
    if getattr(tracer, "enabled", False):
        print(f"[agentic_reviewer] LangSmith tracing enabled (project={tracer.project_name}).")
    session_run_name = f"review-session:{session_identifier}"
    if pr:
        session_run_name += f":pr{pr}"
    session_inputs = {
        "repo": repo,
        "branch": branch,
        "session_id": session_identifier,
        "pr": pr,
        "max_commits": max_commits,
        "pending_commits": len(commits),
    }
    session_id_value = session_run_name
    set_log_session(session_id_value)
    review_run = tracer.start_run(
        name=session_run_name,
        inputs=session_inputs,
    )

    supervisor = Supervisor(repo, repo_path, tracer=tracer, progress_callback=emit)
    results: List[Dict[str, Any]] = []

    previous_session_commit = session_manager.last_commit_sha()
    try:
        for commit in commits:
            base_sha = previous_session_commit or (commit.parents[0].hexsha if commit.parents else None)
            base_commit = None
            if base_sha:
                try:
                    base_commit = repository.commit(base_sha)
                except Exception:
                    base_commit = None
            changed_files_commit, diff_excerpt = _collect_diff_metadata(commit, base_commit=base_commit)
            planning_files = changed_files_commit

            emit("commit_start", commit=commit.hexsha, summary=commit.summary)
            state = execute_review_workflow(
                supervisor,
                commit,
                planning_files,
                diff_excerpt,
                progress_callback=emit,
                parent_run=review_run,
            )

            review = state.get("review", {"findings": []})
            triage_plan = state.get("triage", {})

            report_payload = {
                "repo": repo,
                "branch": branch,
                "pr": pr,
                "commit": commit.hexsha,
                "summary": commit.summary,
                "manifest": state.get("manifest", {}),
                "triage": triage_plan,
                "changed_files": planning_files,
                "tasks": state.get("tasks", []),
                "task_reports": state.get("task_reports", []),
                "tool_results": state.get("tool_results", []),
                "critic": state.get("critic_output", {}),
                "synthesis": state.get("synthesis", {}),
                "node_outputs": state.get("node_outputs", {}),
            }
            report_path = write_report(
                repo,
                commit.hexsha,
                report_payload,
                reports_dir,
            )
            record_findings(repo, commit.hexsha, review.get("findings", []), report_path=report_path)
            record_commit_event(
                repo,
                commit.hexsha,
                summary=commit.summary,
                author=getattr(commit.author, "name", None),
                files_changed=len(planning_files),
            )
            emit("commit_complete", commit=commit.hexsha, findings=len(review.get("findings", [])))

            triage_info = triage_plan or {}
            session_manager.record_commit(
                commit.hexsha,
                commit.summary,
                planning_files=planning_files,
                triage=triage_info,
                findings=review.get("findings", []),
                base_commit=base_sha,
            )
            session_manager.append_comments(commit.hexsha, review.get("findings", []))
            session_manager.save()

            session_snapshot = session_manager.session_summary()
            report_payload["session"] = session_snapshot

            results.append(
                {
                    "commit": commit.hexsha,
                    "summary": commit.summary,
                    "author": getattr(commit.author, "name", None),
                    "committed_at": commit.committed_datetime.isoformat(),
                    "review": review,
                    "manifest": state.get("manifest", {}),
                    "triage": triage_plan,
                    "tasks": state.get("tasks", []),
                    "task_reports": state.get("task_reports", []),
                    "critic": state.get("critic_output", {}),
                    "synthesis": state.get("synthesis", {}),
                    "node_outputs": state.get("node_outputs", {}),
                    "report_path": str(report_path),
                    "session": session_snapshot,
                }
            )

            previous_session_commit = commit.hexsha
        return results
    finally:
        tracer.end_run(review_run, outputs={"result_count": len(results)})
        clear_log_session()
