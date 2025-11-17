from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from llm_utils import build_chat_model, extract_json_response
from memory import session_memory
from tools import rag_tools
from tools.system_tools import ToolResult, command_available, run_command


logger = logging.getLogger(__name__)


MAX_TOOL_SIGNALS = 4
MAX_SIGNAL_OUTPUT_CHARS = 1200
MAX_CONTEXT_CHARS = 600
MAX_CONTEXT_CHUNKS = 2
CACHE_ROOT = Path(".cache") / "llm_repo_agent"

HALLUCINATION_MARKERS = [
    "based on the provided output",
    "based on the provided data",
    "here is a json",
    "here's a json",
    "here is the response",
    "since there are no",
    "note that this response",
]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _trim_chunks(chunks: Optional[List[Dict[str, Any]]], *, limit: int, max_chars: int) -> List[Dict[str, Any]]:
    if not chunks:
        return []
    trimmed: List[Dict[str, Any]] = []
    for chunk in chunks[:limit]:
        text = str(chunk.get("text", ""))
        if len(text) > max_chars:
            chunk = dict(chunk)
            chunk["text"] = _truncate(text, max_chars)
        trimmed.append(chunk)
    return trimmed


class LLMRepoAgent:
    """
    Repo-scoped specialist agent that uses tool output (signals) as evidence
    and asks an LLM to craft actionable findings.
    """

    MAX_OUTPUT_CHARS = 2000

    def __init__(
        self,
        repo_path: Path,
        *,
        name: str,
        specialty: str,
        checklist: Optional[Sequence[str]] = None,
        task_name: Optional[str] = None,
    ):
        self.repo_path = Path(repo_path)
        self.name = name
        self.specialty = specialty
        self.checklist = list(checklist or [])
        self.task_name = task_name or f"{name}_repo_agent"
        self.repo_reference: Optional[str] = None
        try:
            self.chat = build_chat_model(task=self.task_name)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to construct chat model for %s agent: %s", self.name, exc)
            self.chat = None

    # -- hooks -----------------------------------------------------------------

    def set_repo_reference(self, repo_reference: str) -> None:
        self.repo_reference = repo_reference

    def collect_signals(self, commit) -> List[Dict[str, Any]]:  # pragma: no cover - abstract
        """
        Subclasses must run their tools/heuristics and return a list of signals.
        Each signal should describe the evidence (stdout/stderr/message/severity).
        """
        raise NotImplementedError

    # -- public API -------------------------------------------------------------

    def review_repo(self, commit) -> List[Dict]:
        signals = self.collect_signals(commit)
        if not signals:
            diff_signal = self._diff_context_signal(commit)
            if diff_signal:
                signals = [diff_signal]
            else:
                return []

        missing_tool_signals = [signal for signal in signals if signal.get("returncode") == 127]
        actionable_signals = [signal for signal in signals if signal.get("returncode") != 127]

        findings: List[Dict] = []
        if missing_tool_signals:
            findings.extend(self._missing_tool_findings(missing_tool_signals))

        if not actionable_signals:
            return findings

        payload = self._build_payload(actionable_signals, commit)
        messages = self._build_messages(payload)
        if self.chat is None:
            findings.extend(self._fallback_findings(actionable_signals))
            return findings
        try:
            response = self.chat.invoke(messages).content
        except Exception as exc:  # pragma: no cover
            logger.error("%s agent LLM call failed: %s", self.name, exc)
            findings.extend(self._fallback_findings(actionable_signals))
            return findings
        llm_findings = self._normalize_response(response)
        if not llm_findings:
            findings.extend(self._fallback_findings(actionable_signals))
        else:
            findings.extend(llm_findings)
        return findings

    # -- payload + prompt ------------------------------------------------------

    def _build_payload(self, signals: List[Dict[str, Any]], commit) -> Dict[str, Any]:
        summary = getattr(commit, "summary", "") if commit else ""
        commit_hash = getattr(commit, "hexsha", "") if commit else ""
        recent_memory = []
        if self.repo_reference:
            recent_memory = session_memory.load_recent(self.repo_reference, limit=3)
        query = summary or self.specialty
        repo_context = self._fetch_repo_context(query)

        full_payload = {
            "specialty": self.specialty,
            "checklist": self.checklist,
            "signals": signals,
            "commit": {
                "hash": commit_hash,
                "summary": summary,
            },
            "repo_reference": self.repo_reference,
            "recent_memory": recent_memory,
            "code_context": repo_context.get("code"),
            "documentation": repo_context.get("documentation"),
            "best_practices": repo_context.get("best_practices"),
        }
        cache_reference = self._persist_payload(full_payload)

        trimmed_signals = []
        for signal in signals[:MAX_TOOL_SIGNALS]:
            trimmed_signals.append(
                {
                    **signal,
                    "stdout": _truncate(signal.get("stdout", ""), min(self.MAX_OUTPUT_CHARS, MAX_SIGNAL_OUTPUT_CHARS)),
                    "stderr": _truncate(signal.get("stderr", ""), min(self.MAX_OUTPUT_CHARS, MAX_SIGNAL_OUTPUT_CHARS)),
                }
            )

        payload = {
            "specialty": self.specialty,
            "checklist": self.checklist,
            "signals": trimmed_signals,
            "commit": {
                "hash": commit_hash,
                "summary": summary,
            },
            "repo_reference": self.repo_reference,
            "recent_memory": recent_memory,
            "code_context": _trim_chunks(repo_context.get("code"), limit=MAX_CONTEXT_CHUNKS, max_chars=MAX_CONTEXT_CHARS),
            "documentation": _trim_chunks(
                repo_context.get("documentation"),
                limit=MAX_CONTEXT_CHUNKS,
                max_chars=MAX_CONTEXT_CHARS,
            ),
            "best_practices": _trim_chunks(
                repo_context.get("best_practices"),
                limit=MAX_CONTEXT_CHUNKS,
                max_chars=MAX_CONTEXT_CHARS,
            ),
            "cache_reference": cache_reference,
        }
        return payload
    def _persist_payload(self, payload: Dict[str, Any]) -> str:
        commit_hash = payload.get("commit", {}).get("hash") or "nohash"
        cache_id = f"{self.name}_{commit_hash[:8]}_{uuid.uuid4().hex[:8]}"
        try:
            CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            cache_path = CACHE_ROOT / f"{cache_id}.json"
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            return str(cache_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to persist payload for %s: %s", self.name, exc)
            return ""

    def _fetch_repo_context(self, query: str) -> Dict[str, Any]:
        if not (self.repo_reference and query):
            return {"code": [], "documentation": [], "best_practices": []}
        return {
            "code": rag_tools.fetch_code_context(self.repo_reference, query, n_results=2),
            "documentation": rag_tools.fetch_doc_context(self.repo_reference, query, n_results=2),
            "best_practices": rag_tools.fetch_best_practices(self.repo_reference, query, n_results=3),
        }

    def _build_messages(self, payload: Dict[str, Any]) -> List:
        checklist_text = ""
        if self.checklist:
            checklist_text = "Checklist:\n- " + "\n- ".join(self.checklist)
        system_text = (
            f"You are the {self.name} agent. Specialty: {self.specialty}. "
            "Use the evidence and repository memory to emit rigorous review findings."
        )
        instruction = (
            f"{checklist_text}\n"
            "Ground every finding in the tool output or provided context snippets. "
            "Quote the relevant stdout/stderr/documentation in code_line or references. "
            "If you cannot cite concrete evidence, respond with []. "
            "Return a JSON list. Each finding must include rule_id, severity "
            "(blocker|high|medium|low|info), file_path (or \"\"), line, message, "
            "code_line, recommended_fix, and references (dict or list). "
            "Never fabricate files or results."
        ).strip()
        human = HumanMessage(
            content=f"Context:\n```json\n{json.dumps(payload, indent=2)}\n```\n{instruction}"
        )
        return [SystemMessage(content=system_text), human]

    # -- helpers to run tools --------------------------------------------------

    def missing_tool_signal(self, tool_name: str, *, message: Optional[str] = None, severity: str = "info") -> Dict[str, Any]:
        return {
            "tool_name": tool_name,
            "severity": severity,
            "message": message or f"{tool_name} is not installed.",
            "stdout": "",
            "stderr": "",
            "returncode": 127,
        }

    def run_tool(
        self,
        command: Sequence[str],
        *,
        tool_name: str,
        severity: str,
        description: str,
        issue_on: Optional[Sequence[int]] = None,
        success_codes: Sequence[int] = (0,),
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        result = run_command(list(command), self.repo_path, timeout=timeout)
        return self._signal_from_result(
            result,
            tool_name=tool_name,
            severity=severity,
            description=description,
            issue_on=issue_on,
            success_codes=success_codes,
        )

    def _signal_from_result(
        self,
        result: ToolResult,
        *,
        tool_name: str,
        severity: str,
        description: str,
        issue_on: Optional[Sequence[int]] = None,
        success_codes: Sequence[int],
    ) -> Optional[Dict[str, Any]]:
        exit_code = result.returncode
        issue = False
        if issue_on is not None and exit_code in issue_on:
            issue = True
        elif exit_code not in success_codes:
            issue = True

        if not issue:
            return None
        stderr = result.stderr or ""
        stdout = result.stdout or ""
        if result.error:
            stderr = f"{stderr}\n{result.error}".strip()
        return {
            "tool_name": tool_name,
            "severity": severity,
            "message": description,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": exit_code,
            "command": " ".join(result.command),
        }

    @staticmethod
    def tool_available(executable: str) -> bool:
        return command_available(executable)

    # -- normalization ---------------------------------------------------------

    def _diff_context_signal(self, commit) -> Optional[Dict[str, Any]]:
        if commit is None:
            return None
        parents = getattr(commit, "parents", [])
        base = parents[0] if parents else None
        if base is None:
            return None
        try:
            diffs = commit.diff(base, create_patch=True)
        except Exception:
            return None
        excerpts: List[str] = []
        for diff in diffs:
            blob = diff.b_blob or diff.a_blob
            if blob is not None:
                mime = getattr(blob, "mime_type", None)
                if mime and not mime.startswith("text"):
                    continue
                try:
                    chunk = blob.data_stream.read(1024)
                    blob.data_stream.seek(0)
                    if b"\x00" in chunk:
                        continue
                except Exception:
                    continue
            path = diff.b_path or diff.a_path or ""
            if not path or not diff.diff:
                continue
            try:
                patch_text = diff.diff.decode("utf-8", errors="ignore")
            except Exception:
                continue
            excerpts.append(f"File: {path}\n{patch_text[:800]}")
            if len("\n\n".join(excerpts)) > MAX_SIGNAL_OUTPUT_CHARS:
                break
        if not excerpts:
            return None
        stdout = "\n\n".join(excerpts)[:MAX_SIGNAL_OUTPUT_CHARS]
        return {
            "tool_name": "diff_context",
            "severity": "medium",
            "message": "Raw diff context provided for LLM analysis.",
            "stdout": stdout,
            "stderr": "",
            "returncode": 0,
        }

    def _normalize_response(self, response: str) -> List[Dict]:
        response = response.strip()
        if not response:
            return []
        parsed = extract_json_response(response)
        if parsed is None:
            logger.warning("%s agent produced non-JSON response; falling back to tool output.", self.name)
            return []
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            logger.warning(
                "%s agent produced unexpected response type %s; falling back to tool output.",
                self.name,
                type(parsed).__name__,
            )
            return []
        findings: List[Dict] = []
        for item in parsed or []:
            if not isinstance(item, dict):
                continue
            references = self._normalize_references(item.get("references"))
            finding = {
                "agent": self.name,
                "rule_id": item.get("rule_id", f"{self.name.upper()}_LLM"),
                "severity": item.get("severity", "medium"),
                "file_path": item.get("file_path", ""),
                "line": item.get("line", item.get("line_start", 0)) or 0,
                "line_start": item.get("line_start", item.get("line", 0)) or 0,
                "line_end": item.get("line_end", item.get("line", 0)) or 0,
                "message": item.get("message") or item.get("title", "Review finding"),
                "code_line": item.get("code_line", "") or item.get("description", ""),
                "recommended_fix": item.get("recommended_fix") or item.get("suggested_patch", ""),
                "references": references,
            }
            if self._looks_hallucinated(finding["message"]) or self._looks_hallucinated(finding["code_line"]):
                logger.warning("%s agent dropping hallucinated response: %s", self.name, finding["message"][:120])
                continue
            if not finding["code_line"] and not finding["references"]:
                logger.warning("%s agent response lacks evidence; ignoring.", self.name)
                continue
            findings.append(finding)
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

    def _fallback_findings(self, signals: List[Dict[str, Any]]) -> List[Dict]:
        findings: List[Dict] = []
        for signal in signals:
            findings.append(
                {
                    "agent": self.name,
                    "rule_id": f"{self.name.upper()}_SIGNAL",
                    "severity": signal.get("severity", "info"),
                    "file_path": "",
                    "line": 0,
                    "message": f"{signal.get('tool_name')}: {signal.get('message')}",
                    "code_line": signal.get("stdout", "")[:200],
                    "references": {
                        "stderr": signal.get("stderr", "")[:400],
                        "command": signal.get("command", ""),
                    },
                }
            )
        return findings

    def _missing_tool_findings(self, signals: List[Dict[str, Any]]) -> List[Dict]:
        findings: List[Dict] = []
        for signal in signals:
            findings.append(
                {
                    "agent": self.name,
                    "rule_id": f"{self.name.upper()}_MISSING_TOOL",
                    "severity": "info",
                    "file_path": "",
                    "line": 0,
                    "message": f"{signal.get('tool_name')} not available: {signal.get('message')}",
                    "code_line": "",
                    "references": {
                        "command": signal.get("command", ""),
                    },
                }
            )
        return findings

    @staticmethod
    def _looks_hallucinated(text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        if "```" in text:
            return True
        return any(marker in lowered for marker in HALLUCINATION_MARKERS)
