from __future__ import annotations

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
        added_lines = static_analysis.parse_patch(file_path, patch_text)
        issues = static_analysis.detect_security_issues(added_lines)
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
