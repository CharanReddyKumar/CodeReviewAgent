from __future__ import annotations

import argparse

from pathlib import Path

from review_runner import run_review


def _format_finding(index: int, finding: dict) -> str:
    location = f"{finding.get('file_path','')}:{finding.get('line','?')}"
    header = f"{index}. [{finding.get('agent')}|{finding.get('severity')}|{finding.get('rule_id')}] {location}"
    message = finding.get("message", "")
    code_line = finding.get("code_line")
    lines = [header, f"    {message}"]
    if code_line:
        lines.append(f"    ↓ {code_line}")
    references = finding.get("references") or {}
    for ref_name, ref_text in references.items():
        lines.append(f"    ↳ {ref_name}: {ref_text}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the agentic reviewer across recent commits."
    )
    parser.add_argument("repo", help="Repository URL or slug.")
    parser.add_argument("branch", help="Branch or ref to inspect.")
    parser.add_argument(
        "--max-commits",
        type=int,
        default=5,
        help="Number of most recent commits to review (default: 5).",
    )
    parser.add_argument(
        "--refresh-artifacts",
        action="store_true",
        help="Rebuild embeddings and import graph before reviewing.",
    )
    parser.add_argument(
        "--refresh-best-practices",
        action="store_true",
        help="Re-index commit messages into the best-practices store.",
    )
    parser.add_argument(
        "--best-practices-docs",
        help="Folder containing PDF/Markdown/TXT best-practice docs to ingest.",
    )
    parser.add_argument(
        "--force-artifacts",
        action="store_true",
        help="Force regeneration of vector/graph artifacts even if cache matches.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="GitHub pull request number to checkout for review.",
    )
    parser.add_argument(
        "--base",
        help="Base commit/ref to diff against (defaults to previous commit).",
    )
    parser.add_argument(
        "--reports-dir",
        help="Directory to store JSON reports (default: reports/<slug>/).",
    )
    parser.add_argument(
        "--session",
        help="Explicit review session identifier (defaults to branch or PR number).",
    )
    args = parser.parse_args()

    results = run_review(
        args.repo,
        args.branch,
        max_commits=args.max_commits,
        refresh_artifacts=args.refresh_artifacts,
        refresh_best_practices=args.refresh_best_practices,
        best_practices_docs=Path(args.best_practices_docs) if args.best_practices_docs else None,
        force_artifacts=args.force_artifacts,
        pr=args.pr,
        base=args.base,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
        session_id=args.session,
    )

    for result in results:
        review = result.get("review", {"findings": []})
        print(
            f"\n=== Commit {result['commit'][:7]} === {result['summary']}\n"
            f"Author: {result.get('author') or 'unknown'} | {result.get('committed_at')}"
        )
        findings = review.get("findings", [])
        if not findings:
            print("  ✓ No issues detected.")
        else:
            for idx, finding in enumerate(findings, 1):
                print(_format_finding(idx, finding))
        report_path = result.get("report_path")
        if report_path:
            print(f"[agentic_reviewer] JSON report written to {report_path}")


if __name__ == "__main__":
    main()
