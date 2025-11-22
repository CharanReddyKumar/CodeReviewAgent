from __future__ import annotations

import json
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from agents.critic_agent import CodeIssue
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
            "severity (high|medium|low|info), title, message, recommended_fix, references (list of strings), "
            "file_path, line_number, code_snippet, reasoning, rule_id, confidence.\n"
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
            findings = []

        normalized = []
        for item in findings:
            # Map LLM output to CodeIssue fields
            try:
                # Ensure required fields are present or defaulted
                issue_data = {
                    "file_path": item.get("file_path") or item.get("file") or "",
                    "line_number": int(item.get("line_number") or item.get("line") or item.get("line_start") or 0),
                    "code_snippet": item.get("code_snippet") or item.get("code_line") or item.get("message", "")[:50],
                    "confidence": float(item.get("confidence", 0.5)),
                    "reasoning": item.get("reasoning") or item.get("description") or item.get("message", ""),
                    "severity": item.get("severity", "info"),
                    "rule_id": item.get("rule_id", "LLM_REVIEW"),
                }
                
                # Validate with CodeIssue
                issue = CodeIssue(**issue_data)
                
                # If valid, add to normalized list (converting back to dict for compatibility)
                normalized.append(
                    {
                        "agent": self.name,
                        "rule_id": issue.rule_id,
                        "title": item.get("title", "LLM Review"),
                        "severity": issue.severity,
                        "file": issue.file_path,
                        "file_path": issue.file_path,
                        "line_start": issue.line_number,
                        "line_end": issue.line_number,
                        "line": issue.line_number,
                        "category": item.get("category", "style"),
                        "description": issue.reasoning,
                        "message": item.get("title", "LLM Review"),
                        "code_line": issue.code_snippet,
                        "suggested_patch": item.get("suggested_patch") or item.get("recommended_fix"),
                        "recommended_fix": item.get("recommended_fix", ""),
                        "evidence": item.get("evidence"),
                        "references": item.get("references") or [],
                        "confidence": issue.confidence,
                    }
                )
            except Exception as e:
                # Skip invalid items or log them
                print(f"Skipping invalid finding: {e}")
                continue

        return enforce_evidence(normalized)
