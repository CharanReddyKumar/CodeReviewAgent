from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from llm_utils import build_chat_model


class ActionExecutor:
    """LLM-powered executor that handles reasoning actions that are not tied to concrete tools."""

    def __init__(self) -> None:
        self.chat = build_chat_model(task="task_executor")

    def execute(
        self,
        task: Dict[str, Any],
        action: Dict[str, Any],
        manifest: Optional[Dict[str, Any]],
        context_snapshots: List[Dict[str, Any]],
    ) -> str:
        payload = {
            "task": {
                "id": task.get("id"),
                "title": task.get("title"),
                "specialist": task.get("specialist"),
                "files": task.get("files", []),
            },
            "action": {
                "type": action.get("type"),
                "description": action.get("description"),
                "instructions": action.get("instructions"),
                "files": action.get("files", []),
            },
            "manifest": {
                "summary": (manifest or {}).get("summary", ""),
                "priority": (manifest or {}).get("priority", "medium"),
                "high_risk_tags": (manifest or {}).get("high_risk_tags", []),
            },
            "context": context_snapshots,
        }
        system_text = (
            "You are the ExecutionAgent in a multi-step code review workflow. "
            "Use the provided task description, action instructions, and context snippets to outline your reasoning "
            "and the concrete insights you discover. Keep the response under 4 sentences. "
            "Do not fabricate tool results; rely only on the provided context."
        )
        prompt = HumanMessage(content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```\nRespond with plain text.")
        try:
            response = self.chat.invoke([SystemMessage(content=system_text), prompt]).content
        except Exception as exc:  # pragma: no cover - fallback to readable error
            return f"Action execution failed: {exc}"
        return response.strip() or "Action completed without additional notes."
