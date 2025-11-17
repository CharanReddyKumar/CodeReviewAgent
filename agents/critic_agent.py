from __future__ import annotations

import json
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.review_types import CriticOutput, SpecialistFinding
from llm_utils import build_chat_model


class CriticAgent:
    """Final narrator that turns findings + diff into review-ready output."""

    def __init__(self) -> None:
        self.chat = build_chat_model(task="critic")

    def critique(
        self,
        commit_summary: str,
        diff_excerpt: str,
        findings: List[SpecialistFinding],
    ) -> CriticOutput:
        payload = {
            "summary": commit_summary,
            "diff_excerpt": diff_excerpt[:6000],
            "findings": findings,
        }
        system_text = (
            "You are the CriticAgent. Produce (1) executive_summary (<=3 sentences), (2) grouped_comments (list of {file_path, span, severity, message, recommended_fix}), "
            "and (3) follow_ups (list of strings). Use the findings JSON; do not fabricate files not in findings. Return JSON."
        )
        response = self.chat.invoke(
            [
                SystemMessage(content=system_text),
                HumanMessage(content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```"),
            ]
        ).content
        try:
            data = json.loads(response)
            if isinstance(data, dict):
                return CriticOutput(
                    executive_summary=str(data.get("executive_summary", "")).strip(),
                    grouped_comments=data.get("grouped_comments", []),
                    follow_ups=data.get("follow_ups", []),
                )
        except json.JSONDecodeError:
            pass
        return CriticOutput(
            executive_summary=response.strip(),
            grouped_comments=[],
            follow_ups=[],
        )
