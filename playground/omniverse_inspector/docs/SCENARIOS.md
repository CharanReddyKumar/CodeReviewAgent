# Scenario Matrix

This repository intentionally mixes risky patterns so that every review lane has concrete evidence to surface:

| Lane             | Trigger                                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Security**     | `/exec` shell injection, `/inspect/<path>` traversal, yaml loader executing arbitrary constructors, and unbounded sqlite logging.    |
| **Secrets**      | Hard-coded Slack tokens, AWS credentials, and `.env` example files with production credentials.                                      |
| **Performance**  | `scripts/full_report.py` performs cubic-time comparisons, while `src/worker.py` busy-waits on every job.                             |
| **Dependencies** | `requirements.txt` pins stale versions with known CVEs (Flask 2.0.0, Requests 2.20.0, NumPy 1.18.0, PyYAML 5.1).                     |
| **Tests**        | `tests/test_exec_command.py` expects input validation that is intentionally missing, so the suite fails and records regression risk. |
| **Docs**         | This matrix conflicts with `README.md` upgrade guidance so doc agents can flag mismatches.                                           |
| **Style/Type**   | `src/report_generator.py` returns inconsistent types and mixes mutable default arguments.                                            |

When running the full agent workflow, ensure each commit touches multiple areas so the planner schedules security, dependency, and performance tasks together.
