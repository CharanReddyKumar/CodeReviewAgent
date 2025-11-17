from __future__ import annotations

import json
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.review_types import ReviewManifest, SpecialistFinding, TaskReport, SynthesisOutput
from llm_utils import build_chat_model


class SynthesisAgent:
    """Merges specialist findings and produces a normalized summary."""

    def __init__(self) -> None:
        self.chat = build_chat_model(task="synthesis")

    def synthesize(
        self,
        manifest: ReviewManifest,
        reports: List[TaskReport],
    ) -> SynthesisOutput:
        normalized = self._deduplicate(reports)
        summary = self._summarize(manifest, normalized)
        return SynthesisOutput(normalized_findings=normalized, summary=summary)

    def _deduplicate(self, reports: List[TaskReport]) -> List[SpecialistFinding]:
        seen = set()
        normalized: List[SpecialistFinding] = []
        for report in reports:
            for finding in report.get("findings", []) or []:
                key = (
                    finding.get("file_path", ""),
                    finding.get("message", ""),
                    finding.get("rule_id", ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                normalized.append(finding)
        return normalized

    def _summarize(
        self,
        manifest: ReviewManifest,
        findings: List[SpecialistFinding],
    ) -> str:
        if not findings:
            return "No blocking issues detected; specialists reported a clean run."
        payload = {
            "manifest": manifest,
            "findings": findings[:20],  # limit context length
        }
        system_text = (
            "You are the SynthesisAgent. Given normalized findings, write a short narrative (<=5 sentences) summarizing the review state."
        )
        response = self.chat.invoke(
            [
                SystemMessage(content=system_text),
                HumanMessage(content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```"),
            ]
        ).content
        return response.strip()
