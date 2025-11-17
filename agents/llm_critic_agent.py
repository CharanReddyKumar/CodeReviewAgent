from __future__ import annotations

import json
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.evidence_guard import enforce_evidence
from llm_utils import build_chat_model, extract_json_response
from memory import session_memory
from rag.reteriever import RepositoryRetriever


class LLMCriticAgent:
    name = "llm_critic"

    def __init__(self, repo_reference: str, retriever: RepositoryRetriever):
        self.repo_reference = repo_reference
        self.retriever = retriever
        self.chat = build_chat_model(task="critic_draft")

    def _build_prompt(
        self,
        commit_summary: str,
        diff_excerpt: str,
        tool_findings: List[Dict],
        policy_chunks: List[Dict],
        commit_memory: List[Dict],
    ) -> List:
        system_text = (
            "You are an expert Python code reviewer. "
            "Use the provided diffs, tool findings, and best-practice excerpts to write actionable review comments. "
            "Always cite relevant best-practice snippets when possible."
        )

        context = {
            "commit_summary": commit_summary,
            "diff_excerpt": diff_excerpt,
            "tool_findings": tool_findings,
            "policy_context": [
                {"text": chunk["text"], "metadata": chunk["metadata"]}
                for chunk in policy_chunks
            ],
            "recent_memory": commit_memory,
        }
        instruction = (
            "Given the JSON context above, produce a JSON list where each item has:\n"
            "severity (high|medium|low|info), title, message, recommended_fix, references (list of strings).\n"
            "Focus only on real issues. If no issues, return an empty list."
        )
        human = HumanMessage(content=f"Context:\n```json\n{json.dumps(context, indent=2)}\n```\n{instruction}")
        return [SystemMessage(content=system_text), human]

    def review(
        self,
        commit_summary: str,
        diff_excerpt: str,
        tool_findings: List[Dict],
    ) -> List[Dict]:
        policy_chunks = [
            {"text": chunk.text, "metadata": chunk.metadata}
            for chunk in self.retriever.search_policy_docs(commit_summary, n_results=4)
        ]
        recent_memory = session_memory.load_recent(self.repo_reference, limit=3)

        messages = self._build_prompt(
            commit_summary,
            diff_excerpt,
            tool_findings,
            policy_chunks,
            recent_memory,
        )
        try:
            response = self.chat.invoke(messages).content
        except Exception as exc:
            return [
                {
                    "agent": self.name,
                    "rule_id": "LLM_ERROR",
                    "severity": "info",
                    "file_path": "",
                    "line": 0,
                    "message": f"LLM critic failed: {exc}",
                    "code_line": "",
                    "references": {},
                }
            ]

        findings = extract_json_response(response)
        if isinstance(findings, dict):
            findings = [findings]
        if not isinstance(findings, list):
            findings = [
                {
                    "severity": "info",
                    "title": "LLM Review Summary",
                    "message": (response or "").strip(),
                    "recommended_fix": "",
                    "references": [],
                }
            ]

        normalized = []
        for item in findings:
            file_path = item.get("file_path") or item.get("file") or ""
            line_start = item.get("line_start", item.get("line", 0))
            line_end = item.get("line_end", line_start)
            references = item.get("references") or []
            normalized.append(
                {
                    "agent": self.name,
                    "rule_id": "LLM_REVIEW",
                    "title": item.get("title", "LLM Review"),
                    "severity": item.get("severity", "low"),
                    "file": file_path,
                    "file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "line": line_start,
                    "category": item.get("category", "style"),
                    "description": item.get("description", item.get("message", "")),
                    "message": item.get("title", "LLM Review"),
                    "code_line": item.get("message", ""),
                    "suggested_patch": item.get("suggested_patch") or item.get("recommended_fix"),
                    "recommended_fix": item.get("recommended_fix", ""),
                    "evidence": item.get("evidence"),
                    "references": references if isinstance(references, list) else [references],
                }
            )

        return enforce_evidence(normalized)
