from __future__ import annotations

import json
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from llm_utils import build_chat_model, extract_json_response


class ScopeAgent:
    """
    Lightweight classifier that tags the commit with topics and risk signals.
    """

    name = "scope"

    def __init__(self) -> None:
        self.chat = build_chat_model(task="scope")

    def analyze(self, changed_files: List[str], diff_excerpt: str) -> Dict:
        system_prompt = (
            "You are a senior reviewer triage agent. "
            "Given the changed files and diff summary, classify the work by topics "
            "(auth, db, io, concurrency, security, docs, tests, performance, pii, config, build, other) "
            "and emit a numeric risk_score between 0 and 1. "
            "Provide a short justification and any risk_flags (list of strings). "
            "Return JSON with keys: topics (list[str]), risk_score (float), justification (str), risk_flags (list[str])."
        )
        examples = {
            "changed_files": changed_files,
            "diff_excerpt": diff_excerpt[:4000],
        }
        response = self.chat.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Context:\n```json\n{json.dumps(examples, indent=2)}\n```"),
            ]
        ).content
        data = extract_json_response(response)
        if not isinstance(data, dict):
            return {
                "topics": [],
                "risk_score": 0.3,
                "justification": (response or "").strip()[:200],
                "risk_flags": [],
            }
        data.setdefault("topics", [])
        data.setdefault("risk_flags", [])
        data.setdefault("justification", "")
        data["risk_score"] = float(data.get("risk_score", 0.3))
        return data
