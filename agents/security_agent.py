from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from tools import static_analysis


def _reference_snippet(chunks: Optional[List[Dict]]) -> Optional[str]:
    if not chunks:
        return None
    chunk = chunks[0]
    text = chunk.get("text", "").strip()
    if not text:
        return None
    lines = text.splitlines()
    snippet = " ".join(lines[:2])
    source = chunk.get("metadata", {}).get("relative_path") or chunk.get("metadata", {}).get("sha")
    if source:
        return f"{source}: {snippet}"
    return snippet


class SecurityAgent:
    name = "security"

    def review(self, file_path: str, patch_text: str, context: Dict) -> List[Dict]:
        print(f"[DEBUG] SecurityAgent reviewing {file_path}")
        added_lines = static_analysis.parse_patch(file_path, patch_text)
        print(f"[DEBUG] Found {len(added_lines)} added lines in {file_path}")
        if not added_lines:
            repo_root = context.get("repo_path")
            if repo_root:
                full_path = Path(repo_root) / file_path
                if full_path.exists():
                    try:
                        fallback_lines: List[static_analysis.AddedLine] = []
                        with full_path.open("r", encoding="utf-8", errors="ignore") as handle:
                            for idx, line in enumerate(handle, start=1):
                                fallback_lines.append(
                                    static_analysis.AddedLine(
                                        file_path=file_path,
                                        line_no=idx,
                                        content=line.rstrip("\n"),
                                    )
                                )
                        added_lines = fallback_lines
                        print(
                            f"[DEBUG] SecurityAgent fallback scanned {len(added_lines)} total lines in {file_path}"
                        )
                    except OSError as exc:
                        print(f"[DEBUG] SecurityAgent fallback read failed for {file_path}: {exc}")
        issues = static_analysis.detect_security_issues(added_lines)
        print(f"[DEBUG] Found {len(issues)} security issues in {file_path}")
        practices_hint = _reference_snippet(context.get("best_practices"))
        code_hint = _reference_snippet(context.get("code"))
        findings: List[Dict] = []
        for issue in issues:
            references: Dict[str, str] = {}
            message = issue.message
            if practices_hint:
                references["best_practices"] = practices_hint
            if code_hint:
                references["code_context"] = code_hint
            if references:
                message = f"{message} ({'; '.join(references.values())})"
            findings.append(
                {
                    "agent": self.name,
                    "rule_id": issue.rule_id,
                    "severity": issue.severity,
                    "file_path": issue.file_path,
                    "line": issue.line_no,
                    "message": message,
                    "code_line": issue.code_line,
                    "references": references,
                }
            )
        return findings
