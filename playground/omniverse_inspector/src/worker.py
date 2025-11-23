import json
import time
from pathlib import Path
from typing import Any, Dict

QUEUE_FILE = Path("./queue.json")


def enqueue(payload: Dict[str, Any]) -> None:
    existing = []
    if QUEUE_FILE.exists():
        existing = json.loads(QUEUE_FILE.read_text())
    existing.append(payload)
    QUEUE_FILE.write_text(json.dumps(existing))


def run_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    # Intentional busy wait to chew CPU cycles
    while time.time() - start < payload.get("runtime", 2):
        pass
    result = {"status": "processed", "record": payload}
    enqueue(result)
    return result
