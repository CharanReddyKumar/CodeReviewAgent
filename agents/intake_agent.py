from __future__ import annotations

import json
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.review_types import ReviewManifest
from llm_utils import build_chat_model, extract_json_response


class IntakeAgent:
    """LLM-powered intake node that produces a structured manifest."""

    def __init__(self) -> None:
        self.chat = build_chat_model(task="intake")

    def create_manifest(
        self,
        commit_summary: str,
        changed_files: List[str],
        diff_excerpt: str,
        languages: List[str],
    ) -> ReviewManifest:
        examples = {
            "summary": commit_summary,
            "changed_files": changed_files,
            "diff_excerpt": diff_excerpt[:6000],
            "languages": languages,
        }
        system_prompt = (
            "You are the IntakeAgent for a multi-LLM review crew. "
            "Summarize the change set, classify frameworks, and tag high-risk areas (auth, data, crypto, network, performance). "
            "Return JSON with fields: summary, description, files, languages, frameworks, high_risk_tags, size (tiny|small|medium|large|mega), priority (low|medium|high|urgent)."
        )
        response = self.chat.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Context:\n```json\n{json.dumps(examples, indent=2)}\n```"),
            ]
        ).content
        manifest = self._parse_manifest(response, changed_files, languages)
        return manifest

    def _parse_manifest(
        self,
        response: str,
        default_files: List[str],
        languages: List[str],
    ) -> ReviewManifest:
        fallback: ReviewManifest = {
            "summary": "",
            "description": response.strip()[:400],
            "files": default_files,
            "languages": languages,
            "frameworks": [],
            "high_risk_tags": [],
            "size": "medium",
            "priority": "medium",
        }
        data = extract_json_response(response)
        if isinstance(data, dict):
            fallback.update({k: v for k, v in data.items() if v is not None})
            fallback.setdefault("files", default_files)
            fallback.setdefault("languages", languages)
            fallback.setdefault("frameworks", [])
            fallback.setdefault("high_risk_tags", [])
            return fallback
        return fallback
