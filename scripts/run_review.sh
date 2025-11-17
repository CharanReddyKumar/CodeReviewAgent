#!/usr/bin/env bash
set -euo pipefail

PLAYGROUND_REPO="$HOME/Desktop/review-playground"
REVIEWER_ROOT="$HOME/Desktop/CodeReviewAgent"

cd "$REVIEWER_ROOT"
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

python agentic_revewer.py "$PLAYGROUND_REPO" main --max-commits 1 --reports-dir ./reports
