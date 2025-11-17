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
    source = chunk.get("metadata", {}).get("relative_path")
    if source:
        return f"{source}: {snippet}"
    return snippet


class StyleAgent:
    name = "style"

    def review(self, file_path: str, patch_text: str, context: Dict) -> List[Dict]:
        added_lines = static_analysis.parse_patch(file_path, patch_text)
        issues = static_analysis.detect_style_issues(added_lines)
        doc_hint = _reference_snippet(context.get("documentation"))
        best_hint = _reference_snippet(context.get("best_practices"))
        findings: List[Dict] = []
        for issue in issues:
            message = issue.message
            references: Dict[str, str] = {}
            if doc_hint:
                references["documentation"] = doc_hint
            if best_hint:
                references["best_practices"] = best_hint
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
