from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

PATCH_HEADER_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class AddedLine:
    file_path: str
    line_no: int
    content: str


@dataclass
class Issue:
    file_path: str
    line_no: int
    message: str
    severity: str
    rule_id: str
    code_line: str


def parse_patch(file_path: str, patch_text: str) -> List[AddedLine]:
    """
    Extract the added lines and their line numbers from a unified diff patch.
    """
    added_lines: List[AddedLine] = []
    current_line_no = None
    for line in patch_text.splitlines():
        if line.startswith("@@"):
            match = PATCH_HEADER_RE.match(line)
            if match:
                current_line_no = int(match.group(1))
            continue

        if current_line_no is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(
                AddedLine(
                    file_path=file_path,
                    line_no=current_line_no,
                    content=line[1:],
                )
            )
            current_line_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        else:
            if not line.startswith("\\ No newline"):
                current_line_no += 1
    return added_lines


def detect_style_issues(added_lines: List[AddedLine]) -> List[Issue]:
    issues: List[Issue] = []
    for line in added_lines:
        stripped = line.content.rstrip("\n")
        if len(stripped) > 120:
            issues.append(
                Issue(
                    file_path=line.file_path,
                    line_no=line.line_no,
                    message="Line exceeds 120 characters.",
                    severity="low",
                    rule_id="STYLE_LONG_LINE",
                    code_line=stripped,
                )
            )
        if stripped.rstrip(" \t") != stripped:
            issues.append(
                Issue(
                    file_path=line.file_path,
                    line_no=line.line_no,
                    message="Trailing whitespace detected.",
                    severity="low",
                    rule_id="STYLE_TRAILING_WHITESPACE",
                    code_line=stripped,
                )
            )
        if "TODO" in stripped or "FIXME" in stripped:
            issues.append(
                Issue(
                    file_path=line.file_path,
                    line_no=line.line_no,
                    message="Leftover TODO/FIXME comment in committed code.",
                    severity="medium",
                    rule_id="STYLE_TODO",
                    code_line=stripped,
                )
            )
    return issues


SECURITY_PATTERNS = [
    (
        re.compile(r"\beval\("),
        "Avoid using eval() on dynamic input.",
        "SEC_EVAL",
    ),
    (
        re.compile(r"\bexec\("),
        "Avoid using exec() on dynamic input.",
        "SEC_EXEC",
    ),
    (
        re.compile(r"os\.system\("),
        "Prefer subprocess without shell=True instead of os.system.",
        "SEC_OS_SYSTEM",
    ),
    (
        re.compile(r"subprocess\.[a-zA-Z_]+\([^)]*shell\s*=\s*True"),
        "shell=True in subprocess exposes command injection risk.",
        "SEC_SHELL_TRUE",
    ),
    (
        re.compile(r"pickle\.loads\("),
        "Untrusted pickle.loads can execute arbitrary code.",
        "SEC_PICKLE_LOADS",
    ),
]


def detect_security_issues(added_lines: List[AddedLine]) -> List[Issue]:
    issues: List[Issue] = []
    for line in added_lines:
        for pattern, description, rule_id in SECURITY_PATTERNS:
            if pattern.search(line.content):
                issues.append(
                    Issue(
                        file_path=line.file_path,
                        line_no=line.line_no,
                        message=description,
                        severity="high" if rule_id in {"SEC_EVAL", "SEC_EXEC"} else "medium",
                        rule_id=rule_id,
                        code_line=line.content.strip(),
                    )
                )
                break
    return issues
