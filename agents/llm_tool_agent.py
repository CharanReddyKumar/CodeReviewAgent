from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from llm_utils import build_chat_model


logger = logging.getLogger(__name__)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


class LLMToolAgent:
    """
    Base class for file-scoped LLM agents that combine heuristics with retrieval context.
    """

    MAX_PATCH_CHARS = 3200
    MAX_CONTEXT_SNIPPET = 600

    def __init__(
        self,
        name: str,
        specialty: str,
        *,
        checklist: Optional[Sequence[str]] = None,
        task_name: Optional[str] = None,
    ):
        self.name = name
        self.specialty = specialty
        self.checklist = list(checklist or [])
        self.task_name = task_name or f"{name}_agent"
        self.default_rule_id = f"{self.name.upper()}_LLM"
        self.repo_reference: Optional[str] = None
        try:
            self.chat = build_chat_model(task=self.task_name)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to construct chat model for %s: %s", self.name, exc)
            self.chat = None

    def set_repo_reference(self, repo_reference: str) -> None:
        self.repo_reference = repo_reference

    # -- Hooks for subclasses -------------------------------------------------

    def gather_signals(self, file_path: str, patch_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Subclasses can override to provide heuristic hints (e.g., static analysis hits).
        """
        return []

    # -- Public API -----------------------------------------------------------

    def review(self, file_path: str, patch_text: str, context: Dict[str, Any]) -> List[Dict]:
        patch_excerpt = patch_text.strip()
        if not patch_excerpt:
            return []
        patch_excerpt = _truncate_text(patch_excerpt, self.MAX_PATCH_CHARS)

        signals = self.gather_signals(file_path, patch_text, context)
        payload = self._build_payload(file_path, patch_excerpt, context, signals)
        messages = self._build_messages(payload)

        if self.chat is None:
            return self._fallback_from_signals(signals) or self._missing_model_finding()

        try:
            response = self.chat.invoke(messages).content
        except Exception as exc:
            logger.error("%s agent LLM call failed: %s", self.name, exc)
            return self._fallback_from_signals(signals) or self._error_finding(str(exc))

        findings = self._normalize_response(response, file_path)
        if findings:
            return findings
        return self._fallback_from_signals(signals) or self._error_finding("LLM returned no actionable findings.")

    # -- Prompt helpers -------------------------------------------------------

    def _build_payload(
        self,
        file_path: str,
        patch_excerpt: str,
        context: Dict[str, Any],
        signals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        def _trim_chunks(raw: Optional[List[Dict[str, Any]]], limit: int = 3) -> List[Dict[str, Any]]:
            trimmed: List[Dict[str, Any]] = []
            for chunk in (raw or [])[:limit]:
                trimmed.append(
                    {
                        "text": _truncate_text(str(chunk.get("text", "")), self.MAX_CONTEXT_SNIPPET),
                        "metadata": chunk.get("metadata", {}),
                        "score": chunk.get("score"),
                    }
                )
            return trimmed

        payload = {
            "agent": self.name,
            "specialty": self.specialty,
            "file_path": file_path,
            "patch": patch_excerpt,
            "signals": signals,
            "code_context": _trim_chunks(context.get("code")),
            "documentation": _trim_chunks(context.get("documentation")),
            "best_practices": _trim_chunks(context.get("best_practices")),
            "imports": context.get("imports"),
            "recent_memory": (context.get("memory") or [])[:3],
            "repo_reference": context.get("repo_reference"),
        }
        return payload

    def _build_messages(self, payload: Dict[str, Any]) -> List:
        checklist_text = ""
        if self.checklist:
            checklist_text = "Checklist:\n- " + "\n- ".join(self.checklist)

        system_text = (
            f"You are the {self.name} agent. "
            f"Specialty: {self.specialty}. "
            "Collaborate with sibling agents by producing precise, verifiable review findings."
        )
        instruction = (
            f"{checklist_text}\n"
            "Using the JSON payload, emit a JSON list. "
            "Each item must include: rule_id, severity (blocker|high|medium|low|info), "
            "file_path, line, optional line_end, message, code_line, "
            "recommended_fix, and references (dict or list of citations). "
            "Prefer citing policy/best-practices snippets when relevant. "
            "Return [] if no issues in your specialty."
        ).strip()

        human = HumanMessage(
            content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```\n{instruction}"
        )
        return [SystemMessage(content=system_text), human]

    # -- Normalization --------------------------------------------------------

    def _normalize_response(self, response: str, default_file: str) -> List[Dict]:
        response = response.strip()
        if not response:
            return []
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            logger.debug("%s agent returned non-JSON response.", self.name)
            parsed = [{"message": response, "severity": "info"}]

        if isinstance(parsed, dict):
            parsed = [parsed]

        findings: List[Dict] = []
        for item in parsed or []:
            if not isinstance(item, dict):
                continue
            references = self._normalize_references(item.get("references"))
            findings.append(
                {
                    "agent": self.name,
                    "rule_id": item.get("rule_id", self.default_rule_id),
                    "severity": item.get("severity", "medium"),
                    "file_path": item.get("file_path") or default_file,
                    "line": item.get("line", item.get("line_start", 0)) or 0,
                    "line_start": item.get("line_start", item.get("line", 0)) or 0,
                    "line_end": item.get("line_end", item.get("line", 0)) or 0,
                    "message": item.get("message") or item.get("title", "Review finding"),
                    "code_line": item.get("code_line", "") or item.get("description", ""),
                    "recommended_fix": item.get("recommended_fix") or item.get("suggested_patch", ""),
                    "references": references,
                }
            )
        return findings

    @staticmethod
    def _normalize_references(raw: Any) -> Dict[str, str]:
        if not raw:
            return {}
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        if isinstance(raw, list):
            return {f"ref_{idx+1}": str(value) for idx, value in enumerate(raw, start=1)}
        return {"reference": str(raw)}

    def _fallback_from_signals(self, signals: List[Dict[str, Any]]) -> List[Dict]:
        findings: List[Dict] = []
        for signal in signals:
            findings.append(
                {
                    "agent": self.name,
                    "rule_id": signal.get("rule_id", self.default_rule_id),
                    "severity": signal.get("severity", "medium"),
                    "file_path": signal.get("file_path", ""),
                    "line": signal.get("line", 0),
                    "message": signal.get("message", "Potential issue detected."),
                    "code_line": signal.get("code_line", ""),
                    "references": signal.get("references", {}),
                }
            )
        return findings

    def _missing_model_finding(self) -> List[Dict]:
        return [
            {
                "agent": self.name,
                "rule_id": "LLM_MODEL_MISSING",
                "severity": "info",
                "file_path": "",
                "line": 0,
                "message": f"{self.name} agent could not initialize its LLM model.",
                "code_line": "",
                "references": {},
            }
        ]

    def _error_finding(self, message: str) -> List[Dict]:
        return [
            {
                "agent": self.name,
                "rule_id": f"{self.default_rule_id}_ERROR",
                "severity": "info",
                "file_path": "",
                "line": 0,
                "message": message,
                "code_line": "",
                "references": {},
            }
        ]
