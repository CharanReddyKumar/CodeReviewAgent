from __future__ import annotations

from typing import Dict, List

from pydantic import ValidationError

from schemas.finding import Evidence, Finding


def _coerce_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _ensure_schema_fields(entry: Dict) -> Dict:
    data = dict(entry)
    file_path = data.get("file") or data.get("file_path") or ""
    line_start = data.get("line_start", data.get("line") or 0)
    line_end = data.get("line_end", line_start)
    data.setdefault("title", data.get("message", "LLM Review"))
    data.setdefault("file", file_path)
    data.setdefault("file_path", file_path)
    data.setdefault("line_start", _coerce_int(line_start) or 0)
    data.setdefault("line_end", _coerce_int(line_end) or data["line_start"])
    data.setdefault("severity", data.get("severity", "low"))
    data.setdefault("category", data.get("category", "style"))
    data.setdefault("description", data.get("description") or data.get("code_line") or data.get("message", ""))
    evidence = data.get("evidence")
    if not evidence:
        evidence = [
            {
                "type": "code_span",
                "file": data.get("file", ""),
                "start": data.get("line_start", 0),
                "end": data.get("line_end", data.get("line_start", 0)),
            }
        ]
    normalized_evidence = []
    for ev in evidence:
        if isinstance(ev, Evidence):
            normalized_evidence.append(ev.dict())
        elif isinstance(ev, dict):
            ev = ev.copy()
            ev["type"] = ev.get("type", "code_span")
            normalized_evidence.append(ev)
    data["evidence"] = normalized_evidence
    return data


def enforce_evidence(findings: List[Dict]) -> List[Dict]:
    validated: List[Dict] = []
    placeholder_markers = [
        "based on the provided output",
        "based on the provided data",
        "here is a json list",
        "note that i've assumed",
        "note that this is",
    ]
    for entry in findings:
        candidate = _ensure_schema_fields(entry)
        message = candidate.get("message", "").lower()
        file_path = candidate.get("file_path", "")
        if any(marker in message for marker in placeholder_markers):
            continue
        if file_path.startswith("/path/to"):
            continue
        schema_payload = {
            "title": candidate.get("title"),
            "severity": candidate.get("severity"),
            "file": candidate.get("file"),
            "line_start": candidate.get("line_start"),
            "line_end": candidate.get("line_end"),
            "category": candidate.get("category"),
            "description": candidate.get("description"),
            "suggested_patch": candidate.get("suggested_patch"),
            "evidence": candidate.get("evidence"),
            "references": candidate.get("references"),
        }
        try:
            Finding(**schema_payload)
        except ValidationError:
            continue
        candidate["evidence"] = [Evidence(**ev).dict() if isinstance(ev, dict) else ev for ev in candidate["evidence"]]
        validated.append(candidate)
    return validated
