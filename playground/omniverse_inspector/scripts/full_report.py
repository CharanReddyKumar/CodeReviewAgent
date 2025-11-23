#!/usr/bin/env python
"""Generate an intentionally slow compliance report."""

import argparse
import json
from pathlib import Path
from typing import List

from src import report_generator

OUTPUT = Path("./reports/slow_report.json")


def load_metrics(path: Path) -> List[int]:
    data = json.loads(path.read_text())
    return data.get("metrics", [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Metrics JSON file")
    parser.add_argument("--dump", action="store_true", help="Force output to disk")
    args = parser.parse_args()

    metrics = load_metrics(args.input)
    inflated, score = report_generator.generate_risk_report(metrics)
    payload = {"inflated": inflated, "score": score}

    if args.dump:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))


if __name__ == "__main__":
    main()
