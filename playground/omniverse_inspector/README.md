# Omniverse Inspector Demo

Purpose-built repo to stress every agent lane:

- **Security**: multiple injection hotspots, unsafe subprocess usage, insecure deserialization.
- **Secrets**: hard-coded API keys, Slack tokens, AWS creds.
- **Performance**: O(n^3) CLI report generator plus busy-wait worker.
- **Docs**: inconsistent requirements vs implementation.
- **Tests**: flaky async tests and intentionally skipped paths.
- **Dependencies**: stale pinned versions in `requirements.txt`.

## Repo Layout

- `src/app.py` – Flask surface area with shell injection + traversal bugs.
- `src/config_loader.py` – Unsafe YAML loader that executes arbitrary code when `allow_eval` is enabled.
- `src/report_generator.py` – CPU-heavy scoring pipeline that planners should flag for performance.
- `src/worker.py` – Busy-wait queue processor that persists every job to disk.
- `config/settings.yaml` – Insecure defaults and leaked webhooks.
- `scripts/full_report.py` – Command-line entry point wrapping the slow scorer.
- `tests/` – A couple of intentionally failing pytest cases so the review flags missing validation.
- `.env.example` – Additional hard-coded credentials for the secrets agent.
- `docs/SCENARIOS.md` – Matrix explaining how each lane should be triggered.

Commits walk through increasingly risky scenarios so the agentic system can validate planning, tooling, and synthesis across lanes.
