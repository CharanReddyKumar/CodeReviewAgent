from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

import json

from agent_registry import get_tool_specs
from llm_utils import build_chat_model

MANIFEST_PATH = Path("planner_manifest.json")


def _load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"agents": []}
    return {"agents": []}


def _risk_score(scope: Dict[str, Any]) -> float:
    try:
        return float(scope.get("risk_score", 0.3))
    except Exception:
        return 0.3


def _topics(scope: Dict[str, Any]) -> List[str]:
    topics = scope.get("topics") or []
    if isinstance(topics, list):
        return [str(topic) for topic in topics]
    return []


def plan_tools(
    languages: List[str],
    changed_files: List[str],
    repo_path: str,
    scope: Dict[str, Any] | None = None,
) -> List[str]:
    specs = get_tool_specs(languages)
    tool_summaries = [
        {
            "id": spec.id,
            "scope": spec.scope,
            "description": spec.description,
            "languages": spec.languages,
        }
        for spec in specs
    ]

    scope_payload = scope or {}
    manifest = _load_manifest()
    prompt = (
        "You are an autonomous review planner for a coding agent. Decide which tools to run.\n"
        "Tools:\n"
        f"{json.dumps(tool_summaries, indent=2)}\n\n"
        f"Planner manifest:\n{json.dumps(manifest, indent=2)}\n\n"
        f"Changed files: {changed_files}\n"
        f"Scope info: {json.dumps(scope_payload, indent=2)}\n"
        "Return a JSON list of tool IDs, sorted by priority, only including tools relevant to the changed files/languages.\n"
        "Each entry may optionally be an object with fields {id, reason, max_seconds}. "
        "Include at least one tool per language if available. If parsing fails, default to running everything."
    )
    chat = build_chat_model(task="planner")
    try:
        response = chat.invoke(prompt).content
        plan = json.loads(response)
        if isinstance(plan, list):
            normalized: List[str] = []
            for item in plan:
                if isinstance(item, str):
                    normalized.append(item)
                elif isinstance(item, dict) and "id" in item:
                    normalized.append(str(item["id"]))
            if normalized:
                return normalized
    except Exception:
        pass
    # fallback risk-aware plan
    fallback = []
    base_topics = _topics(scope_payload)
    score = _risk_score(scope_payload)
    for spec in specs:
        if spec.scope == "file" or spec.id.startswith("python_style"):
            fallback.append(spec.id)
        elif spec.scope == "repo":
            if spec.id.endswith("security") and (score >= 0.6 or any(topic in {"auth", "pii", "secrets"} for topic in base_topics)):
                fallback.append(spec.id)
            elif spec.id.endswith("performance") and score >= 0.7:
                fallback.append(spec.id)
            else:
                fallback.append(spec.id)
    return fallback
