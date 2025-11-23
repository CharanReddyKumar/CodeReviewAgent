# Full-System Validation Plan

## Goals

- Exercise every LangGraph node (`intake` through `finalize`) under realistic commit reviews.
- Trigger each specialist agent family (style, format, lint, correctness/tests, security, dependency, performance, docs, memory, planner, critic).
- Validate retrieval-quality paths (RAG best-practice embeddings, Chroma vector store) and knowledge-graph ingestion.
- Observe artifact persistence (reports, review JSON) and ensure findings propagate end-to-end.
- Capture success/failure evidence for each run so regressions are obvious.

## Scenario Matrix

| Scenario | Repo                                                         | Purpose                                                                                                                 | Modules exercised                                                                                                                                     |
| -------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1       | `playground/vulpy` (existing)                                | Realistic Python web app w/ known vulns; verifies security, dependency, performance, lint, formatting lanes             | intake, context, triage, planner, tasks, security agent, semgrep, style, format, tests, lint, type, performance, dependency, critic, memory, finalize |
| S2       | `playground/full_system_demo` (new)                          | Curated multi-feature repo mixing Python, docs, configs to stress planners, doc+scope agents, embeddings, graph linking | all nodes + doc_agent, context_agent, doc ingestion, memory lane, RAG embeddings                                                                      |
| S3       | `playground/full_system_demo` second commit                  | Small documentation-only change to test planner down-scoping and critic follow-ups                                      | intake, context, triage, planner, doc agent, critic replan                                                                                            |
| S4       | (optional) `playground/full_system_demo` performance profile | Force heavy benchmark path + type agent gating by enabling large test config                                            | performance_agent, type_agent re-run                                                                                                                  |

## Test Workflow

1. **Repo Preparation**

   - `full_system_demo` repo contains:
     - `src/` Python module with mixed code issues (unused imports, unsafe APIs, type errors, flaky tests).
     - `services/` with async worker to trigger concurrency heuristics.
     - `docs/` referencing best practices to validate doc agent + RAG snippets.
     - `infra/` YAML manifest with secrets to trigger secrets_agent.
     - `requirements.txt` pinned to vulnerable libs for dependency agent.
     - `tests/` purposely failing to ensure tests_agent + performance_agent results.
   - Repo initialized with Git history so multiple commits can be reviewed.

2. **Execution Harness**

   - Add script `scripts/full_system_diagnostic.py` to sequentially run `agentic_revewer.py` for each scenario, capturing:
     - CLI/stdout log (saved under `logs/system_runs/<timestamp>/`).
     - Generated JSON report path for each commit.
     - Extracted stats: findings count, agents executed, RAG doc ingestion counts, embedding store hits, graph node/edge counts.

3. **Validation Criteria**

   - **RAG / Embeddings**: best-practice ingestion should succeed (no `PdfReadError`), at least N documents ingested, embeddings retrieved for context packets.
   - **Knowledge Graph**: `knowledge_graph` builder logs node/edge counts; script records them and asserts thresholds (>50 nodes for VulnPy, >20 for demo repo).
   - **Agent Coverage**: diagnostic script ensures each specialized agent returns at least one action/result; fail if any lane missing.
   - **Findings Propagation**: `finalize` node must report non-empty findings for scenarios with known issues; script inspects JSON report for `findings` length.
   - **Critic Replan**: Scenario S3 should show critic summary referencing doc-only change and no false positives from other lanes.

4. **Reporting**

   - Diagnostic script generates `reports/system_validation_<timestamp>.md` summarizing:
     - Scenario metadata
     - Agents triggered & counts
     - Key findings (security, tests, etc.)
     - RAG/graph metrics
     - Follow-up TODOs

5. **Regression Hooks**
   - Add `scripts/system_validation.sh` wrapper for CI/manual invocation (optional future work).
   - Document usage in README snippet.

## Next Steps

1. Implement `full_system_demo` repo with curated issues + commits.
2. Build `scripts/full_system_diagnostic.py` harness.
3. Run scenarios S1–S3, capture outputs.
4. Analyze coverage gaps + fix outstanding ingestion errors.
