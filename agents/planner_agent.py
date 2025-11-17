from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.review_types import ContextPacket, PlannerTask, ReviewManifest, TriagePlan
from llm_utils import build_chat_model, extract_json_response

SPECIALISTS = [
    {"id": "style", "description": "Style & formatting review"},
    {"id": "correctness", "description": "Tests, lint, type coverage"},
    {"id": "security", "description": "Security, secrets, auth"},
    {"id": "performance", "description": "Performance-sensitive code"},
    {"id": "dependency", "description": "Dependencies and packages"},
    {"id": "docs", "description": "Docs and public API"},
]


LANE_TOOL_PREFS = {
    "style": ["python_style", "python_format"],
    "security": ["python_security", "python_secrets", "python_semgrep"],
    "tests": ["python_tests"],
    "performance": ["python_performance"],
    "docs": ["python_doc"],
    "api_contract": ["python_dependency", "python_type"],
}


class PlannerAgent:
    """LLM planner that decomposes the manifest into specialist tasks."""

    def __init__(self) -> None:
        self.chat = build_chat_model(task="planner")

    def create_tasks(
        self,
        manifest: ReviewManifest,
        context_packets: List[ContextPacket],
        triage_plan: TriagePlan,
        tool_summaries: List[Dict[str, Any]],
    ) -> List[PlannerTask]:
        payload = {
            "manifest": manifest,
            "context_packets": [
                {k: v for k, v in packet.items() if k not in {"rag_code", "rag_docs", "rag_best_practices", "patch"}}
                for packet in context_packets
            ],
            "specialists": SPECIALISTS,
            "tools": tool_summaries,
            "triage_plan": triage_plan,
        }
        system_text = (
            "You are the PlannerAgent. Given the intake manifest and context packets, produce tasks for the specialists. "
            "Each task must include id, title, specialist (one of: style, correctness, security, performance, dependency, docs), "
            "files, priority (low|medium|high|urgent), budget (xs|s|m|l), risks, optional notes, tool_ids (subset of available tools), "
            "and actions (ordered list). Actions describe how the specialist proceeds. "
            "Allowed action types: analysis (thinking/strategy), tool (explicit tool execution), or note (communicate warnings). "
            "Each action must include type, description, optional instructions, and optional tool_ids/files overrides. "
            "Return JSON list only."
        )
        response = self.chat.invoke(
            [
                SystemMessage(content=system_text),
                HumanMessage(content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```"),
            ]
        ).content
        tasks = self._parse_tasks(response, manifest, context_packets, tool_summaries)
        tasks = self._ensure_lane_coverage(tasks, manifest, context_packets, triage_plan, tool_summaries)
        if not tasks:
            tasks = self._triage_driven_tasks(manifest, context_packets, triage_plan, tool_summaries)
        return tasks

    def _parse_tasks(
        self,
        response: str,
        manifest: ReviewManifest,
        packets: List[ContextPacket],
        tools: List[Dict[str, Any]],
    ) -> List[PlannerTask]:
        all_tool_ids = [tool["id"] for tool in tools]
        data = extract_json_response(response)
        if isinstance(data, list):
            parsed: List[PlannerTask] = []
            for idx, raw in enumerate(data):
                if not isinstance(raw, dict):
                    continue
                specialist = str(raw.get("specialist", "")).lower() or "style"
                files = raw.get("files") or [p["file_path"] for p in packets]
                requested_tools = raw.get("tool_ids") or all_tool_ids
                actions = self._normalize_actions(raw.get("actions"), requested_tools, files)
                parsed.append(
                    PlannerTask(
                        id=str(raw.get("id", f"task_{idx}")),
                        title=raw.get("title", "Review"),
                        specialist=specialist,
                        files=files,
                        priority=str(raw.get("priority", "medium")),
                        budget=str(raw.get("budget", "m")),
                        notes=raw.get("notes", ""),
                        risks=raw.get("risks", manifest.get("high_risk_tags", [])),
                        context_ids=raw.get("context_ids", [packet["id"] for packet in packets]),
                        tool_ids=requested_tools,
                        actions=actions,
                    )
                )
            if parsed:
                return parsed
        # fallback heuristic: create one task per specialist referencing entire manifest
        fallback: List[PlannerTask] = []
        for idx, spec in enumerate(SPECIALISTS):
            fallback.append(
                PlannerTask(
                    id=f"auto_{spec['id']}_{idx}",
                    title=f"{spec['description']}",
                    specialist=spec["id"],
                    files=[packet["file_path"] for packet in packets],
                    priority="high" if spec["id"] in {"security", "performance"} else "medium",
                    budget="m",
                    notes=manifest.get("description", "")[:200],
                    risks=manifest.get("high_risk_tags", []),
                    context_ids=[packet["id"] for packet in packets],
                    tool_ids=all_tool_ids,
                    actions=self._default_actions(all_tool_ids, [packet["file_path"] for packet in packets]),
                )
            )
        return fallback

    def _normalize_actions(
        self,
        raw_actions,
        default_tools: List[str],
        default_files: List[str],
    ) -> List[Dict[str, Any]]:

        def _normalized_type(value: str) -> str:
            normalized = (value or "").lower()
            if normalized in {"analysis", "tool", "note"}:
                return normalized
            return "analysis"

        actions: List[Dict[str, Any]] = []
        if isinstance(raw_actions, list):
            for raw in raw_actions:
                if not isinstance(raw, dict):
                    continue
                action_type = _normalized_type(str(raw.get("type", "analysis")))
                description = raw.get("description") or raw.get("title") or ""
                instructions = raw.get("instructions", raw.get("notes", ""))
                files = raw.get("files") or default_files
                tool_ids = []
                if action_type == "tool":
                    requested = raw.get("tool_ids") or raw.get("tools") or []
                    tool_ids = [tool for tool in requested if tool in default_tools] or default_tools
                actions.append(
                    {
                        "type": action_type,
                        "description": description,
                        "instructions": instructions,
                        "files": files,
                        "tool_ids": tool_ids,
                    }
                )
        if actions:
            return actions
        return self._default_actions(default_tools, default_files)

    @staticmethod
    def _default_actions(tool_ids: List[str], files: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "analysis",
                "description": "Review the diff and context to set the inspection strategy.",
                "instructions": "Summarize risks, affected components, and what to pay attention to before running any tools.",
                "files": files,
                "tool_ids": [],
            },
            {
                "type": "tool",
                "description": "Execute the selected tools to gather findings.",
                "instructions": "",
                "files": files,
                "tool_ids": tool_ids,
            },
        ]

    def _ensure_lane_coverage(
        self,
        planned_tasks: List[PlannerTask],
        manifest: ReviewManifest,
        packets: List[ContextPacket],
        triage_plan: TriagePlan,
        tool_summaries: List[Dict[str, Any]],
    ) -> List[PlannerTask]:
        """
        Ensure every lane chosen during triage has a corresponding specialist task so downstream
        agents always perform the codex-style plan → analyze → tool workflow.
        """
        triage_tasks = self._triage_driven_tasks(manifest, packets, triage_plan, tool_summaries)
        if not planned_tasks:
            return triage_tasks

        existing_specialists = {str(task.get("specialist", "")).lower() for task in planned_tasks}
        appended = False
        for triage_task in triage_tasks:
            specialist = str(triage_task.get("specialist", "")).lower()
            if not specialist or specialist in existing_specialists:
                continue
            planned_tasks.append(triage_task)
            existing_specialists.add(specialist)
            appended = True

        if appended:
            priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
            planned_tasks.sort(key=lambda task: priority_order.get(task.get("priority", "medium"), 2))
        return planned_tasks

    def _triage_driven_tasks(
        self,
        manifest: ReviewManifest,
        packets: List[ContextPacket],
        triage_plan: TriagePlan,
        tool_summaries: List[Dict[str, Any]],
    ) -> List[PlannerTask]:
        if not triage_plan:
            return []
        all_tool_ids = [tool["id"] for tool in tool_summaries]
        available = set(all_tool_ids)
        lane_files: Dict[str, set] = {lane: set() for lane in triage_plan.get("lanes", [])}
        decisions = triage_plan.get("decisions", []) or []
        for decision in decisions:
            file_path = decision.get("file_path")
            for lane in decision.get("lanes", []) or []:
                lane_files.setdefault(lane, set()).add(file_path)
        tasks: List[PlannerTask] = []
        priority = str(triage_plan.get("overall_risk", "medium"))
        risk_budget = {"low": "s", "medium": "m", "high": "l"}
        budget = risk_budget.get(priority, "m")
        for idx, (lane, files) in enumerate(lane_files.items()):
            if not lane:
                continue
            desired_tools = LANE_TOOL_PREFS.get(lane, all_tool_ids)
            resolved_tools = [tool for tool in desired_tools if tool in available] or all_tool_ids
            task_files = [f for f in sorted(files) if f] or [packet["file_path"] for packet in packets]
            tasks.append(
                PlannerTask(
                    id=f"lane_{lane}_{idx}",
                    title=f"{lane.title()} lane review",
                    specialist=lane,
                    files=task_files,
                    priority=priority,
                    budget=budget,
                    notes="triage-driven lane",
                    risks=manifest.get("high_risk_tags", []),
                    context_ids=[packet["id"] for packet in packets],
                    tool_ids=resolved_tools,
                    actions=self._default_actions(resolved_tools, task_files),
                )
            )
        return tasks
