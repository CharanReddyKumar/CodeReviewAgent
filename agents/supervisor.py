from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from agent_registry import detect_languages, instantiate_tools
from graph_defination import normalize_repo_reference
from tools import rag_tools
from telemetry.langsmith import LangSmithTracer

from agents.complexity_agent import ComplexityAgent
from agents.dependency_agent import DependencyAgent
from agents.doc_agent import DocAgent
from agents.format_agent import FormatAgent
from agents.llm_critic_agent import LLMCriticAgent
from agents.lint_agent import LintAgent
from agents.performance_agent import PerformanceAgent
from agents.semgrep_agent import SemgrepAgent
from agents.security_agent import SecurityAgent
from agents.secrets_agent import SecretsAgent
from agents.style_agent import StyleAgent
from agents.test_agent import TestAgent
from agents.type_agent import TypeAgent
from memory import session_memory
from rag.reteriever import RepositoryRetriever

logger = logging.getLogger(__name__)


class Supervisor:
    """
    Coordinates individual specialist agents and aggregates their findings.
    """

    def __init__(
        self,
        repo_reference: str,
        repo_path: Path,
        *,
        tracer: Optional[LangSmithTracer] = None,
        languages: Optional[List[str]] = None,
    ):
        self.repo_reference = normalize_repo_reference(repo_reference)
        self.repo_path = Path(repo_path)
        self.tracer = tracer or LangSmithTracer()
        self.retriever = RepositoryRetriever(self.repo_reference)

        detected_languages = languages or detect_languages(self.repo_path)
        self.languages = [lang.lower() for lang in detected_languages]
        logger.info(
            "Supervisor initialized for languages: %s",
            ", ".join(self.languages),
        )

        self.file_tools = instantiate_tools(
            self.languages,
            scope="file",
            repo_reference=self.repo_reference,
            repo_path=self.repo_path,
        )
        if not self.file_tools:
            logger.warning("No file-level tools found via registry; using defaults.")
            self.file_tools = self._fallback_file_tools()

        self.repo_tools = instantiate_tools(
            self.languages,
            scope="repo",
            repo_reference=self.repo_reference,
            repo_path=self.repo_path,
        )
        if not self.repo_tools:
            logger.warning("No repo-level tools found via registry; using defaults.")
            self.repo_tools = self._fallback_repo_tools()

        self.llm_agent = LLMCriticAgent(self.repo_reference, self.retriever)

    @staticmethod
    def _module_name_from_path(file_path: str) -> str:
        path = PurePosixPath(file_path)
        if path.suffix != ".py":
            return ""
        module = ".".join(path.with_suffix("").parts)
        return module

    def _build_context(self, file_path: str, query: str) -> Dict:
        context = {
            "code": rag_tools.fetch_code_context(self.repo_reference, query, n_results=3),
            "documentation": rag_tools.fetch_doc_context(self.repo_reference, query, n_results=2),
            "best_practices": rag_tools.fetch_best_practices(self.repo_reference, query, n_results=2),
        }
        module_name = self._module_name_from_path(file_path)
        if module_name:
            context["imports"] = rag_tools.fetch_import_context(
                self.repo_reference,
                module_name,
                depth=1,
            )
        return context

    def _fallback_file_tools(self) -> List:
        return [StyleAgent(), SecurityAgent()]

    def _fallback_repo_tools(self) -> List:
        return [
            FormatAgent(self.repo_path),
            LintAgent(self.repo_path),
            TypeAgent(self.repo_path),
            TestAgent(self.repo_path),
            DocAgent(self.repo_path),
            ComplexityAgent(self.repo_path),
            DependencyAgent(self.repo_path),
            SecretsAgent(self.repo_path),
            SemgrepAgent(self.repo_path),
            PerformanceAgent(self.repo_path),
        ]

    def _tool_selected(self, tool, plan: Optional[List[str]]) -> bool:
        if not plan:
            return True
        tool_id = getattr(tool, "tool_id", getattr(tool, "name", tool.__class__.__name__))
        return tool_id in plan

    def _review_file(self, file_path: str, patch_text: str, query: str, commit_run, plan: Optional[List[str]]) -> List[Dict]:
        context = self._build_context(file_path, query)
        findings: List[Dict] = []
        for agent in self.file_tools:
            if not self._tool_selected(agent, plan):
                continue
            agent_run = self.tracer.child_run(
                commit_run,
                name=f"{agent.name}:{file_path}",
                inputs={"file_path": file_path, "query": query},
            )
            try:
                agent_findings = agent.review(file_path, patch_text, context)
                self.tracer.end_run(agent_run, outputs={"findings": agent_findings})
                findings.extend(agent_findings)
            except Exception as exc:
                self.tracer.end_run(agent_run, error=str(exc))
                findings.append(
                    {
                        "agent": getattr(agent, "name", agent.__class__.__name__),
                        "rule_id": "AGENT_ERROR",
                        "severity": "info",
                        "file_path": file_path,
                        "line": 0,
                        "message": f"{agent.__class__.__name__} failed: {exc}",
                        "code_line": "",
                        "references": {},
                    }
                )
        return findings

    @staticmethod
    def _is_binary_diff(diff) -> bool:
        blob = diff.b_blob or diff.a_blob
        if blob is None:
            return False
        mime = getattr(blob, "mime_type", None)
        if mime and not mime.startswith("text"):
            return True
        try:
            # Read a small chunk to check for NULL bytes.
            chunk = blob.data_stream.read(1024)
            return b"\x00" in chunk
        except Exception:
            return False

    def review_commit(self, commit, plan: Optional[List[str]] = None) -> Dict:
        commit_run = self.tracer.start_run(
            name=f"review:{commit.hexsha[:7]}",
            inputs={"commit": commit.hexsha, "summary": commit.summary},
        )
        diff_excerpts: List[str] = []
        try:
            if not commit.parents:
                result = {
                    "commit": commit.hexsha,
                    "summary": commit.summary,
                    "findings": [],
                    "notes": "Initial commit – no parent to diff against.",
                }
                self.tracer.end_run(commit_run, outputs=result)
                return result

            parent = commit.parents[0]
            diffs = commit.diff(parent, create_patch=True)
            findings: List[Dict] = []
            for diff in diffs:
                if self._is_binary_diff(diff):
                    continue
                file_path = diff.b_path or diff.a_path or ""
                if not file_path:
                    continue
                patch_bytes = diff.diff
                if patch_bytes is None:
                    continue
                patch_text = patch_bytes.decode("utf-8", errors="ignore")
                if not patch_text.strip():
                    continue
                query = f"{file_path} {commit.summary}"
                findings.extend(self._review_file(file_path, patch_text, query, commit_run, plan))
                diff_excerpts.append(f"File: {file_path}\n{patch_text[:2000]}")

            for agent in self.repo_tools:
                if not self._tool_selected(agent, plan):
                    continue
                agent_run = self.tracer.child_run(
                    commit_run,
                    name=f"{agent.name}:repo",
                    inputs={"agent": agent.name},
                )
                try:
                    repo_findings = agent.review_repo(commit)
                    findings.extend(repo_findings)
                    self.tracer.end_run(agent_run, outputs={"findings": repo_findings})
                except Exception as exc:
                    self.tracer.end_run(agent_run, error=str(exc))
                    findings.append(
                        {
                            "agent": getattr(agent, "name", agent.__class__.__name__),
                            "rule_id": "AGENT_ERROR",
                            "severity": "info",
                            "file_path": "",
                            "line": 0,
                            "message": f"{agent.__class__.__name__} failed: {exc}",
                            "code_line": "",
                            "references": {},
                        }
                    )

            if self.llm_agent:
                diff_excerpt = "\n\n".join(diff_excerpts)[:4000]
                llm_run = self.tracer.child_run(
                    commit_run,
                    name="llm_critic",
                    inputs={"summary": commit.summary},
                )
                critic_findings = self.llm_agent.review(
                    commit.summary,
                    diff_excerpt,
                    findings,
                )
                self.tracer.end_run(llm_run, outputs={"findings": critic_findings})
                findings.extend(critic_findings)
                session_memory.append_memory(
                    self.repo_reference,
                    {
                        "commit": commit.hexsha,
                        "summary": commit.summary,
                        "highlights": [f.get("message", "") for f in critic_findings],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            result = {
                "commit": commit.hexsha,
                "summary": commit.summary,
                "findings": findings,
            }
            self.tracer.end_run(commit_run, outputs={"result": result})
            return result
        except Exception as exc:
            self.tracer.end_run(commit_run, error=str(exc))
            raise
