from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.review_types import ReviewManifest, TriagePlan
from llm_utils import build_chat_model, extract_json_response


DEFAULT_LANES = ["style", "security", "tests", "performance", "docs", "api_contract"]


class TriageAgent:
    """LLM-powered triage agent that classifies changed files and chooses review lanes."""

    def __init__(self) -> None:
        self.chat = build_chat_model(task="triage")

    def run_triage(
        self,
        manifest: ReviewManifest,
        context_packets: List[Dict[str, Any]],
        diff_excerpt: str,
    ) -> TriagePlan:
        payload = {
            "manifest": manifest,
            "context_packets": [
                {
                    "id": packet.get("id"),
                    "file_path": packet.get("file_path"),
                    "module": packet.get("module"),
                    "neighbors": packet.get("neighbors"),
                }
                for packet in context_packets
            ],
            "diff_excerpt": diff_excerpt[:6000],
            "lanes": DEFAULT_LANES,
        }
        system_text = (
            "You are the ChangeTriageAgent. Analyze the diff summary and context packets. "
            "Classify each file's risk (low|medium|high) and file_type (api|db|infra|tests|docs|security|general). "
            "Select the review lanes required (style|security|tests|performance|docs|api_contract). "
            "Return JSON with keys: overall_risk, lanes (global list), decisions (list of {file_path, risk, file_type, lanes, notes}), recommendations (list of strings)."
        )
        response = self.chat.invoke(
            [
                SystemMessage(content=system_text),
                HumanMessage(content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```"),
            ]
        ).content
        return self._parse_response(response, manifest, context_packets)

    def _parse_response(
        self,
        response: str,
        manifest: ReviewManifest,
        context_packets: List[Dict[str, Any]],
    ) -> TriagePlan:
        default_plan: TriagePlan = {
            "overall_risk": manifest.get("priority", "medium") or "medium",
            "lanes": DEFAULT_LANES[:3],
            "decisions": [
                {
                    "file_path": packet.get("file_path", ""),
                    "risk": "medium",
                    "file_type": "general",
                    "lanes": DEFAULT_LANES[:3],
                    "notes": manifest.get("summary", ""),
                }
                for packet in context_packets
            ],
            "recommendations": [],
        }
        data = extract_json_response(response)
        if isinstance(data, dict):
            plan: TriagePlan = {
                "overall_risk": data.get("overall_risk", default_plan["overall_risk"]) or "medium",
                "lanes": data.get("lanes") or DEFAULT_LANES[:3],
                "decisions": data.get("decisions", []),
                "recommendations": data.get("recommendations", []),
            }
            if not plan["decisions"]:
                plan["decisions"] = default_plan["decisions"]
            return plan
        return default_plan
