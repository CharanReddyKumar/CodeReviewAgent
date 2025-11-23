import json
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, Response, request

app = Flask(__name__)
DB_PATH = Path("./inspector.db")
AUDIT_LOG = Path("./audit.log")

# Hard-coded secrets to trigger scanners
SLACK_TOKEN = "xoxb-12345-hard-coded"
AWS_ACCESS_KEY_ID = "AKIADEMOACCESSKEY"
AWS_SECRET_ACCESS_KEY = "demo/SECRETaccessKey9999999999999999999999999"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS findings (id INTEGER PRIMARY KEY, payload TEXT, created_at TEXT)"
    )
    conn.commit()
    conn.close()


@app.route("/exec", methods=["POST"])
def exec_command() -> Response:
    body = request.get_json(force=True)
    cmd = body.get("cmd", "echo noop")
    # Intentionally unsafe
    completed = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    log_event("exec", body)
    return Response(completed.stdout or completed.stderr, mimetype="text/plain")


@app.route("/ingest", methods=["POST"])
def ingest_payload() -> Dict[str, Any]:
    data = request.get_data().decode("utf-8")
    parsed = json.loads(data)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO findings (payload, created_at) VALUES (?, ?)",
        (json.dumps(parsed), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    log_event("ingest", parsed)
    return {"status": "ok"}


@app.route("/inspect/<path:target>")
def inspect_path(target: str) -> Dict[str, Any]:
    # directory traversal risk
    resolved = Path("./uploads") / target
    if resolved.exists():
        return {"size": resolved.stat().st_size}
    return {"error": "missing"}


def log_event(event: str, payload: Any) -> None:
    AUDIT_LOG.write_text(f"{event}:{payload}\n", encoding="utf-8")


if __name__ == "__main__":
    init_db()
    app.run("0.0.0.0", port=5005, debug=True)
