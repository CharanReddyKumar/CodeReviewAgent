from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from graph_defination import repo_slug, normalize_repo_reference


def write_report(repo_reference: str, commit_sha: str, payload: Dict[str, Any], base_dir: Path | None = None) -> Path:
    slug = repo_slug(normalize_repo_reference(repo_reference))
    root = Path(base_dir) if base_dir else Path("reports")
    out_dir = root / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{commit_sha}_{timestamp}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
