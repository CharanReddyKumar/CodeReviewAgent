from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agent_registry import detect_languages, get_tool_specs, instantiate_tools
from graph_defination import normalize_repo_reference
from tools import rag_tools
from telemetry.langsmith import LangSmithTracer
from memory import session_memory
from memory import preferences as preference_memory

from agents.context_agent import ContextAgent
from agents.intake_agent import IntakeAgent
from agents.memory_agent import MemoryAgent
from agents.planner_agent import PlannerAgent
from agents.review_types import (
    CriticOutput,
    PlannerTask,
    ReviewManifest,
    TriagePlan,
    SpecialistFinding,
    TaskReport,
)
from agents.synthesis_agent import SynthesisAgent
from agents.critic_agent import CriticAgent
from agents.triage_agent import TriageAgent
from rag.reteriever import RepositoryRetriever
from agents.executor_agent import ActionExecutor

logger = logging.getLogger(__name__)


class Supervisor:
    """
    Coordinates individual specialist agents and aggregates their findings.
    """

    @dataclass
    class FileReviewContext:
        file_path: str
        patch_text: str
        query: str
        context: Dict[str, Any]

    def __init__(
        self,
        repo_reference: str,
        repo_path: Path,
        *,
        tracer: Optional[LangSmithTracer] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        languages: Optional[List[str]] = None,
    ):
        self.repo_reference = normalize_repo_reference(repo_reference)
        self.repo_path = Path(repo_path)
        self.tracer = tracer or LangSmithTracer()
        self.progress_callback = progress_callback
        rag_tools.register_repo_path(self.repo_reference, self.repo_path)
        self.retriever = RepositoryRetriever(self.repo_reference, repo_path=self.repo_path)

        detected_languages = languages or detect_languages(self.repo_path)
        self.languages = [lang.lower() for lang in detected_languages]
        logger.info(
            "Supervisor initialized for languages: %s",
            ", ".join(self.languages),
        )

        self.intake_agent = IntakeAgent()
        self.triage_agent = TriageAgent()
        self.context_agent = ContextAgent(self.repo_reference, self.retriever, repo_path=self.repo_path)
        self.planner_agent = PlannerAgent()
        self.synthesis_agent = SynthesisAgent()
        self.critic_agent = CriticAgent(repo_path=self.repo_path)
        self.memory_agent = MemoryAgent()
        self.executor_agent = ActionExecutor()
        
        # Initialize Graph Components
        from knowledge_graph.graph_store import GraphStore
        from agents.cartographer_agent import CartographerAgent
        self.graph_store = GraphStore()
        self.cartographer_agent = CartographerAgent(self.graph_store)

        self.tool_specs = self._load_tool_specs()
        self.tool_instances = self._instantiate_tool_instances()

    def _emit_progress(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        if not self.progress_callback:
            return
        payload = data.copy() if data else {}
        payload.setdefault("repo", self.repo_reference)
        try:
            self.progress_callback(event, payload)
        except Exception:
            pass

    def _load_tool_specs(self) -> Dict[str, Any]:
        specs: Dict[str, Any] = {}
        planner_summaries: List[Dict[str, Any]] = []
        for scope in ("file", "repo"):
            scoped_specs = get_tool_specs(self.languages, scope=scope)
            for spec in scoped_specs:
                specs[spec.id] = spec
                planner_summaries.append(
                    {
                        "id": spec.id,
                        "scope": spec.scope,
                        "description": spec.description,
                        "languages": spec.languages,
                    }
                )
        self._planner_tool_summaries = planner_summaries
        return specs

    def _instantiate_tool_instances(self) -> Dict[str, Any]:
        instances: Dict[str, Any] = {}
        for scope in ("file", "repo"):
            tools = instantiate_tools(
                self.languages,
                scope=scope,
                repo_reference=self.repo_reference,
                repo_path=self.repo_path,
            )
            for tool in tools:
                tool_id = getattr(tool, "tool_id", tool.__class__.__name__)
                instances[tool_id] = tool
        return instances

    def planner_tool_inventory(self) -> List[Dict[str, Any]]:
        return list(self._planner_tool_summaries)

    @staticmethod
    def _module_name_from_path(file_path: str) -> str:
        path = PurePosixPath(file_path)
        if path.suffix != ".py":
            return ""
        module = ".".join(path.with_suffix("").parts)
        return module

    def _build_context(self, file_path: str, query: str, patch_text: str) -> Dict:
        structured = rag_tools.build_structured_context(
            self.repo_reference,
            file_path=file_path,
            patch_text=patch_text,
            query=query,
        )
        context = {
            "code": structured.get("scoped_code", []),
            "documentation": structured.get("scoped_docs", []),
            "best_practices": structured.get("best_practices", []),
            "policy_docs": structured.get("policy_docs", []),
            "symbol_context": structured.get("symbol_context", []),
            "tests": structured.get("related_tests", []),
            "lexical": structured.get("lexical_hits", []),
            "scoped_neighbors": structured.get("neighbors", []),
            "structured": structured,
        }
        module_name = self._module_name_from_path(file_path)
        if module_name:
            context["imports"] = rag_tools.fetch_import_context(
                self.repo_reference,
                module_name,
                depth=1,
            )
        context["memory"] = session_memory.load_recent(self.repo_reference, limit=3)
        pref_summary = preference_memory.summarize_patterns(self.repo_reference)
        memory_patterns: List[Dict[str, Any]] = []
        for action, entries in pref_summary.items():
            for entry in entries:
                pattern = dict(entry)
                pattern["action"] = action
                memory_patterns.append(pattern)
        context["memory_patterns"] = memory_patterns
        context["repo_reference"] = self.repo_reference
        context["repo_path"] = str(self.repo_path)
        return context

    @staticmethod
    def _is_binary_diff(diff) -> bool:
        blob = diff.b_blob or diff.a_blob
        if blob is None:
            return False
        mime = getattr(blob, "mime_type", None)
        if mime and not mime.startswith("text"):
            return True
        try:
            # Read a small chunk to check for NULL bytes.
            chunk = blob.data_stream.read(1024)
            return b"\x00" in chunk
        except Exception:
            return False

    def prepare_file_contexts(self, commit) -> List["Supervisor.FileReviewContext"]:
        parent = commit.parents[0]
        diffs = commit.diff(parent, create_patch=True)
        contexts: List[Supervisor.FileReviewContext] = []
        self._emit_progress(
            "file_contexts_start",
            {"commit": commit.hexsha, "file_count": len(diffs)},
        )
        for diff in diffs:
            if self._is_binary_diff(diff):
                continue
            file_path = diff.b_path or diff.a_path or ""
            if not file_path:
                continue
            patch_bytes = diff.diff
            if patch_bytes is None:
                continue
            patch_text = patch_bytes.decode("utf-8", errors="ignore")
            if not patch_text.strip():
                continue
            query = f"{file_path} {commit.summary}"
            context = self._build_context(file_path, query, patch_text)
            contexts.append(
                Supervisor.FileReviewContext(
                    file_path=file_path,
                    patch_text=patch_text,
                    query=query,
                    context=context,
                )
            )
        self._emit_progress(
            "file_contexts_ready",
            {"commit": commit.hexsha, "contexts": len(contexts)},
        )
        return contexts

    @staticmethod
    def _select_contexts(target_files: List[str], contexts: List["Supervisor.FileReviewContext"]) -> List["Supervisor.FileReviewContext"]:
        if not target_files:
            return contexts
        targets = set(target_files)
        selected = [ctx for ctx in contexts if ctx.file_path in targets]
        return selected or contexts

    @staticmethod
    def _normalize_references(references: Any) -> Dict[str, str]:
        if isinstance(references, dict):
            return {str(k): str(v) for k, v in references.items()}
        if isinstance(references, list):
            return {str(idx): str(value) for idx, value in enumerate(references)}
        return {}

    @staticmethod
    def _confidence_from_evidence(
        references: Dict[str, str],
        code_line: str,
        agent: str,
        severity: Any,
    ) -> str:
        score = 0
        if references:
            score += 1
        if code_line:
            score += 1
        if any(key for key in references if "best" in key.lower() or "doc" in key.lower()):
            score += 1
        severity_label = str(severity or "").lower()
        if severity_label in {"blocker", "high"}:
            score += 1
        if agent and ("tool" in agent.lower() or "python_" in agent.lower()):
            score += 1
        if score >= 4:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def _normalize_finding(self, raw: Dict[str, Any], default_agent: str) -> SpecialistFinding:
        file_path = raw.get("file_path") or raw.get("file") or ""
        line_start = raw.get("line_start", raw.get("line", 0))
        line_end = raw.get("line_end", raw.get("line", line_start))
        span = ""
        if line_start and line_end:
            span = str(line_start) if line_start == line_end else f"{line_start}-{line_end}"
        references = self._normalize_references(raw.get("references"))
        confidence = self._confidence_from_evidence(
            references,
            raw.get("code_line") or raw.get("snippet", ""),
            raw.get("agent") or default_agent,
            raw.get("severity"),
        )
        return SpecialistFinding(
            agent=raw.get("agent") or default_agent,
            file_path=file_path,
            span=span,
            severity=str(raw.get("severity", "info")),
            category=raw.get("category", default_agent),
            message=raw.get("message", raw.get("description", "")),
            recommended_fix=raw.get("recommended_fix", raw.get("suggested_patch", "")),
            references=references,
            code_line=raw.get("code_line", ""),
            rule_id=str(raw.get("rule_id", default_agent.upper())),
            confidence=confidence,
            citations=[f"{key}: {value}" for key, value in references.items()],
        )

    @staticmethod
    def _normalize_action_plan(task: PlannerTask, default_tools: List[str]) -> List[Dict[str, Any]]:
        files = task.get("files", [])
        plan: List[Dict[str, Any]] = []
        for raw in task.get("actions") or []:
            if not isinstance(raw, dict):
                continue
            action_type = str(raw.get("type", "analysis")).lower()
            if action_type not in {"analysis", "tool", "note"}:
                action_type = "analysis"
            plan.append(
                {
                    "type": action_type,
                    "description": raw.get("description", ""),
                    "instructions": raw.get("instructions", raw.get("notes", "")),
                    "files": raw.get("files", files),
                    "tool_ids": raw.get("tool_ids", default_tools),
                }
            )
        if plan:
            return plan
        return [
            {
                "type": "analysis",
                "description": "Study the context and outline the inspection focus.",
                "instructions": "Summarize primary risks, affected files, and any testing strategy before using tools.",
                "files": files,
                "tool_ids": [],
            },
            {
                "type": "tool",
                "description": "Run the specialist tool suite on the scoped files.",
                "instructions": "",
                "files": files,
                "tool_ids": default_tools,
            },
        ]

    def _resolve_action_tools(self, action: Dict[str, Any], fallback: List[str]) -> List[str]:
        requested = action.get("tool_ids") or fallback
        valid = [tool_id for tool_id in requested if tool_id in self.tool_instances]
        return valid or fallback

    @staticmethod
    def _context_snapshot(contexts: List["Supervisor.FileReviewContext"], limit: int = 2) -> List[Dict[str, Any]]:
        snapshots: List[Dict[str, Any]] = []
        for ctx in contexts[:limit]:
            structured = ctx.context.get("structured") or {}
            snapshots.append(
                {
                    "file_path": ctx.file_path,
                    "patch_excerpt": (ctx.patch_text or "")[:600],
                    "risk_tags": structured.get("risk_tags", []),
                    "related_tests": [
                        test.get("file_path", str(test)) for test in (structured.get("related_tests") or [])[:3]
                    ],
                }
            )
        return snapshots

    def _run_file_tool(
        self,
        tool,
        contexts: List["Supervisor.FileReviewContext"],
        tool_id: str,
    ) -> List[SpecialistFinding]:
        findings: List[SpecialistFinding] = []
        for ctx in contexts:
            try:
                raw_findings = tool.review(ctx.file_path, ctx.patch_text, ctx.context)
            except Exception as exc:
                raw_findings = [
                    {
                        "file_path": ctx.file_path,
                        "message": f"{tool_id} failed: {exc}",
                        "severity": "info",
                        "rule_id": "TOOL_ERROR",
                    }
                ]
            for raw in raw_findings or []:
                result = self._normalize_finding(raw, tool_id)
                if not result.get("file_path"):
                    result["file_path"] = ctx.file_path
                findings.append(result)
        return findings

    def _run_repo_tool(self, tool, commit, tool_id: str) -> List[SpecialistFinding]:
        try:
            raw_findings = tool.review_repo(commit)
        except Exception as exc:
            raw_findings = [
                {
                    "file_path": "",
                    "message": f"{tool_id} failed: {exc}",
                    "severity": "info",
                    "rule_id": "TOOL_ERROR",
                }
            ]
        return [self._normalize_finding(raw, tool_id) for raw in raw_findings or []]

    def run_task(
        self,
        task: PlannerTask,
        file_contexts: List["Supervisor.FileReviewContext"],
        commit,
        commit_run,
        manifest: Optional[ReviewManifest] = None,
    ) -> TaskReport:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        task_run = self.tracer.child_run(
            commit_run,
            name=f"task:{task.get('id')}",
            inputs={"tool_ids": task.get("tool_ids", [])},
        )
        tool_ids = [tool_id for tool_id in task.get("tool_ids", []) if tool_id in self.tool_instances]
        if not tool_ids:
            tool_ids = [tool_id for tool_id in self.tool_instances.keys()]
        contexts = self._select_contexts(task.get("files", []), file_contexts)
        action_plan = self._normalize_action_plan(task, tool_ids)
        findings: List[SpecialistFinding] = []
        action_results: List[Dict[str, Any]] = []
        reasoning_notes: List[str] = []
        executed_tools: List[str] = []
        self._emit_progress(
            "task_start",
            {
                "task": task.get("id"),
                "title": task.get("title"),
                "tools": tool_ids,
                "files": task.get("files", []),
                "actions": action_plan,
                "commit": commit.hexsha,
            },
        )
        
        for idx, action in enumerate(action_plan, start=1):
            action_type = str(action.get("type", "analysis")).lower()
            description = action.get("description") or f"Action {idx}"
            action_files = action.get("files", task.get("files", []))
            targeted_contexts = self._select_contexts(action_files, contexts) if action_files else contexts
            if not targeted_contexts:
                targeted_contexts = contexts
            snapshots = self._context_snapshot(targeted_contexts)
            action_payload = {
                "task": task.get("id"),
                "task_title": task.get("title"),
                "description": description,
                "type": action_type,
                "index": idx,
                "commit": commit.hexsha,
            }
            self._emit_progress("task_action", {**action_payload, "status": "start"})
            action_run = self.tracer.child_run(
                task_run,
                name=f"action:{task.get('id')}:{idx}",
                inputs={"type": action_type, "description": description},
            )
            
            if action_type == "note":
                output = action.get("instructions") or description
                reasoning_notes.append(f"{description}: {output}")
                action_results.append(
                    {
                        "type": action_type,
                        "description": description,
                        "output": output,
                        "tool_ids": [],
                        "files": action_files,
                        "findings": 0,
                    }
                )
                self.tracer.end_run(action_run, outputs={"note": output})
                self._emit_progress("task_action", {**action_payload, "status": "complete", "output": output})
                continue

            if action_type == "analysis":
                output = self.executor_agent.execute(task, action, manifest or {}, snapshots)
                reasoning_notes.append(f"{description}: {output}")
                action_results.append(
                    {
                        "type": action_type,
                        "description": description,
                        "output": output,
                        "tool_ids": [],
                        "files": action_files,
                        "findings": 0,
                    }
                )
                self.tracer.end_run(action_run, outputs={"notes": output})
                self._emit_progress("task_action", {**action_payload, "status": "complete", "output": output})
                continue

            if action_type == "graph_query":
                query = action.get("query")
                output = self.cartographer_agent.act({"type": "tool", "tool": "run_cypher", "args": {"query": query}})
                reasoning_notes.append(f"{description}: {output}")
                action_results.append(
                    {
                        "type": action_type,
                        "description": description,
                        "output": str(output),
                        "tool_ids": [],
                        "files": action_files,
                        "findings": 0,
                    }
                )
                self.tracer.end_run(action_run, outputs={"graph_result": str(output)})
                self._emit_progress("task_action", {**action_payload, "status": "complete", "output": str(output)})
                continue

            selected_tools = self._resolve_action_tools(action, tool_ids)
            action_finding_count = 0
            
            # Parallel Execution Logic
            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_tool = {}
                for tool_id in selected_tools:
                    tool = self.tool_instances.get(tool_id)
                    spec = self.tool_specs.get(tool_id)
                    if tool is None or spec is None:
                        findings.append(
                            self._normalize_finding(
                                {
                                    "agent": tool_id,
                                    "message": f"Tool '{tool_id}' is not available for this repo.",
                                    "severity": "info",
                                    "rule_id": "MISSING_TOOL",
                                },
                                tool_id,
                            )
                        )
                        continue
                    
                    self._emit_progress(
                        "tool_start",
                        {
                            "tool": tool_id,
                            "scope": spec.scope,
                            "task": task.get("id"),
                            "commit": commit.hexsha,
                        },
                    )
                    
                    if spec.scope == "file":
                        scoped_contexts = targeted_contexts or contexts
                        future = executor.submit(self._run_file_tool, tool, scoped_contexts, tool_id)
                    else:
                        future = executor.submit(self._run_repo_tool, tool, commit, tool_id)
                    
                    future_to_tool[future] = (tool_id, spec)

                for future in as_completed(future_to_tool):
                    tool_id, spec = future_to_tool[future]
                    tool_findings = []
                    try:
                        tool_findings = future.result()
                    except Exception as exc:
                        logger.error(f"Tool {tool_id} failed: {exc}")
                        tool_findings = [
                            self._normalize_finding(
                                {
                                    "agent": tool_id,
                                    "message": f"Tool execution failed: {exc}",
                                    "severity": "info",
                                    "rule_id": "EXECUTION_ERROR",
                                },
                                tool_id
                            )
                        ]
                    
                    findings.extend(tool_findings)
                    
                    # Tracer update (simplified as we can't easily nest async in sync tracer)
                    # self.tracer.end_run(tool_run, outputs={"finding_count": len(tool_findings)})
                    
                    self._emit_progress(
                        "tool_complete",
                        {
                            "tool": tool_id,
                            "task": task.get("id"),
                            "findings": len(tool_findings),
                            "commit": commit.hexsha,
                        },
                    )
                    if tool_findings:
                        preview = tool_findings[:5]
                        self._emit_progress(
                            "tool_findings",
                            {
                                "tool": tool_id,
                                "task": task.get("id"),
                                "findings": preview,
                                "total_findings": len(tool_findings),
                                "commit": commit.hexsha,
                            },
                        )
                    action_finding_count += len(tool_findings)

            executed_tools.extend(selected_tools)
            action_results.append(
                {
                    "type": "tool",
                    "description": description,
                    "output": "",
                    "tool_ids": selected_tools,
                    "files": action_files,
                    "findings": action_finding_count,
                }
            )
            self.tracer.end_run(action_run, outputs={"finding_count": action_finding_count})
            self._emit_progress(
                "task_action",
                {**action_payload, "status": "complete", "findings": action_finding_count},
            )
        self.tracer.end_run(task_run, outputs={"finding_count": len(findings)})
        self._emit_progress(
            "task_complete",
            {
                "task": task.get("id"),
                "findings": len(findings),
                "commit": commit.hexsha,
            },
        )
        return TaskReport(
            task_id=task.get("id", ""),
            title=task.get("title", ""),
            tool_ids=executed_tools or tool_ids,
            findings=findings,
            notes="\n".join(reasoning_notes).strip(),
            action_results=action_results,
        )

    def run_intake(
        self,
        commit_summary: str,
        changed_files: List[str],
        diff_excerpt: str,
        commit_run,
    ) -> ReviewManifest:
        intake_run = self.tracer.child_run(
            commit_run,
            name="intake",
            inputs={"files": changed_files},
        )
        try:
            manifest = self.intake_agent.create_manifest(
                commit_summary,
                changed_files,
                diff_excerpt,
                self.languages,
            )
            self.tracer.end_run(intake_run, outputs={"manifest": manifest})
            return manifest
        except Exception as exc:
            self.tracer.end_run(intake_run, error=str(exc))
            raise

    def build_context_packets(
        self,
        manifest: ReviewManifest,
        file_contexts: List["Supervisor.FileReviewContext"],
        commit_run,
    ):
        context_run = self.tracer.child_run(
            commit_run,
            name="context",
            inputs={"file_count": len(file_contexts)},
        )
        try:
            packets = self.context_agent.build_context_packets(manifest, file_contexts)
            self.tracer.end_run(context_run, outputs={"packets": packets})
            return packets
        except Exception as exc:
            self.tracer.end_run(context_run, error=str(exc))
            raise

    def run_triage(
        self,
        manifest: ReviewManifest,
        context_packets,
        diff_excerpt: str,
        commit_run,
    ) -> TriagePlan:
        triage_run = self.tracer.child_run(
            commit_run,
            name="triage",
            inputs={"file_count": len(context_packets)},
        )
        try:
            plan = self.triage_agent.run_triage(manifest, context_packets, diff_excerpt)
            self.tracer.end_run(triage_run, outputs={"lanes": plan.get("lanes", [])})
            return plan
        except Exception as exc:
            self.tracer.end_run(triage_run, error=str(exc))
            raise

    def plan_tasks(
        self,
        manifest: ReviewManifest,
        context_packets,
        triage_plan: TriagePlan,
        commit_run,
    ) -> List[PlannerTask]:
        planner_run = self.tracer.child_run(
            commit_run,
            name="planner",
            inputs={"tools": [tool["id"] for tool in self.planner_tool_inventory()]},
        )
        try:
            tasks = self.planner_agent.create_tasks(
                manifest,
                context_packets,
                triage_plan,
                self.planner_tool_inventory(),
            )
            self.tracer.end_run(planner_run, outputs={"tasks": tasks})
            return tasks
        except Exception as exc:
            self.tracer.end_run(planner_run, error=str(exc))
            raise

    def synthesize_findings(
        self,
        manifest: ReviewManifest,
        reports: List[TaskReport],
        commit_run,
    ):
        synthesis_run = self.tracer.child_run(
            commit_run,
            name="synthesis",
            inputs={"report_count": len(reports)},
        )
        try:
            result = self.synthesis_agent.synthesize(manifest, reports)
            self.tracer.end_run(synthesis_run, outputs={"summary": result.get("summary")})
            return result
        except Exception as exc:
            self.tracer.end_run(synthesis_run, error=str(exc))
            raise

    def critique(
        self,
        commit_summary: str,
        diff_excerpt: str,
        findings,
        commit_run,
    ) -> CriticOutput:
        critic_run = self.tracer.child_run(
            commit_run,
            name="critic",
            inputs={"finding_count": len(findings)},
        )
        try:
            # Use the new CriticAgent's validation logic
            critique_result = self.critic_agent.critique_all(findings)
            
            # Construct the CriticOutput expected by the workflow
            output = {
                "executive_summary": f"Critique complete. Approved: {len(critique_result['approved'])}, Rejected: {len(critique_result['rejected'])}",
                "follow_ups": [], # Could be populated if we had a follow-up generation step
                "grouped_comments": critique_result['approved'], # We only pass approved findings forward
                "requires_correction": critique_result['requires_correction'],
                "rejected_findings": critique_result['rejected']
            }
            
            self.tracer.end_run(critic_run, outputs={"exec_summary": output.get("executive_summary", "")})
            return output
        except Exception as exc:
            self.tracer.end_run(critic_run, error=str(exc))
            raise

    def record_memory(self, commit, summary: str, findings) -> None:
        self.memory_agent.record(
            self.repo_reference,
            commit.hexsha,
            summary,
            findings,
        )
