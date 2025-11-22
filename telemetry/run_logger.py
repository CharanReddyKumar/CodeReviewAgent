from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_SESSION: ContextVar[Optional[str]] = ContextVar("run_logger_session", default=None)
LOG_DIR = Path("logs/review_runs")


def set_session(session_id: Optional[str]) -> None:
    _SESSION.set(session_id)


def current_session() -> Optional[str]:
    return _SESSION.get()


def clear_session() -> None:
    _SESSION.set(None)


def log_event(event: str, payload: Optional[Dict[str, Any]] = None, *, session_id: Optional[str] = None) -> None:
    session = session_id or current_session()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "session_id": session,
        "payload": payload or {},
    }
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_path = LOG_DIR / f"{datetime.now(timezone.utc):%Y%m%d}.ndjson"
        with file_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Logging must never break the main flow
        pass
