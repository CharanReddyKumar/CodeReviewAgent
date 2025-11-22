# The Architecture of Autonomous Code Review: Synergizing LangGraph, RAG, and GraphRAG

This paper captures how the current Agentic Reviewer codebase already combines LangGraph orchestration, hybrid RAG, and graph-grounded reasoning, while also calling out the deltas that remain against the desired fully autonomous architecture.

---

## 1. Introduction: The Agentic Shift in Software Engineering
- **Current posture.** `review_runner.run_review` wires an end-to-end pipeline that clones the repo, refreshes vector + graph artifacts, launches the LangGraph workflow per commit, and archives results in JSON reports and session memory (`review_runner.py:77-210`, `review_runner.py:300-360`).
- **Agentic workflow.** LangGraph nodes invoke specialists via the `Supervisor`, allowing iterative reasoning reminiscent of a human reviewer, including telemetry hooks and contextual progress streaming (`workflow.py:10-205`, `review_runner.py:106-210`).
- **Beyond static tooling.** Graph-backed retrieval (import graphs + symbol graphs) combined with semantic search and heuristics provides richer understanding than linters alone (`rag/reteriever.py:152-440`, `knowledge_graph/code_graph.py:125-217`).
- **Open gaps.** The orchestration today is still linear (no reflexive loops), there is no Tree-sitter ETL, and no explicit Graph Query Agent or deterministic AST-based entity resolution yet. These are documented per section below.

---

## 2. Theoretical Framework: The Triad of Agency, Semantics, and Structure

### 2.1 LangGraph: The Operating System for Agents
- **Implemented today.** `workflow.ReviewState` codifies every field the graph manipulates (changed files, triage, tasks, findings, HITL hooks) and `StateGraph` chains the nine nodes (intake → context → triage → planner → tasks → synthesis → critic → memory → finalize) with streaming notifications (`workflow.py:10-205`).
- **Stateful execution.** `execute_review_workflow` injects the Supervisor plus per-commit metadata into the graph and persists LangSmith runs for time-travel debugging (`workflow.py:232-315`).
- **Gap.** Graph checkpoints, rollback/pause hooks, and reflexion loops are not configured. Adding LangGraph checkpointers plus conditional edges would unlock the pause/reflect behavior described in the spec.

### 2.2 The RAG Dichotomy: Vector vs. Graph
- **Vector RAG in practice.** `rag/vector_store.index_repository` chunks code/doc files, tags them with risk + module metadata, and stores them in Chroma for cosine-similarity lookups (`rag/vector_store.py:243-360`).
- **Graph RAG in practice.** `rag/graph_store.build_import_graph` indexes Python modules + import edges, while `knowledge_graph/code_graph.build_code_structure_graph` extracts file/class/function nodes plus `defines`/`calls` edges (`rag/graph_store.py:55-118`, `knowledge_graph/code_graph.py:125-217`).
- **Hybrid retriever.** `RepositoryRetriever.build_context_bundle` fans queries across the vector store, import graph, code graph, lexical BM25, best-practice commits, and policy docs to return a structured context packet (`rag/reteriever.py:305-403`).
- **Gap.** Graph traversal today is bounded to import/symbol proximity. There is no generalized Cypher-like query interface or deterministic multi-hop reasoning exposed to agents yet. Entity resolution for cross-module call targets is also heuristic.

| Feature | Vector RAG (Current) | GraphRAG (Current) | Gap to Target |
| --- | --- | --- | --- |
| Data model | Chunked documents with risk + module tags (`rag/vector_store.py:243-360`) | NetworkX graphs for imports and symbols (`rag/graph_store.py:55-118`, `knowledge_graph/code_graph.py:125-217`) | Need AST-resolved edges across languages and policy graphs accessible via a query agent |
| Retrieval logic | Approximate cosine via Chroma | Deterministic neighbors via `_candidate_paths`, `import_neighborhood`, and `_symbol_context` (`rag/reteriever.py:275-403`) | Missing arbitrary path queries, centrality ranking, and provenance constraints |
| Context window | Top-k chunks plus trimmed lexical snippets (`rag/reteriever.py:77-150`, `agents/context_agent.py:29-79`) | Immediate module neighbors + related tests | Need graph compression / community selection and summarized neighbors |
| Reasoning type | Semantic similarity for code/comments | Structural hints (imports, symbol spans, best-practice provenance) | Need Cypher-based “Cartographer” agent + taint-style multi-hop tracing |

---

## 3. Architectural Foundations: The Codebase Knowledge Graph (CKG)

### 3.1 Ontology of Code
- **Implemented nodes.** Files, classes, functions, and async functions are materialized with module, span, summaries, and “contracts” metadata (`knowledge_graph/code_graph.py:125-166`).
- **Implemented edges.** `defines` edges link files → symbols and `calls` edges link caller → callee when names match, giving a lightweight execution graph (`knowledge_graph/code_graph.py:167-210`).
- **Gap.** The ontology currently stops at variables and packages; there are no explicit `imports`, `inherits`, or `taints` edges in the CKG layer. Extending the schema plus storing in Neo4j/FalkorDB would enable richer reasoning.

### 3.2 Parsing Engine: Tree-sitter vs. AST
- **Current parser.** The pipeline uses Python’s stdlib `ast` module for Python files (`knowledge_graph/code_graph.py:125-210`). It gracefully skips files that fail to parse but lacks incremental reparsing or polyglot support.
- **Gap.** Tree-sitter bindings, language-agnostic parsing, and entity-resolution (“merge” phase to match symbol references to definitions across modules) are not implemented yet. These are prerequisites for 100% precise dependency tracing.

### 3.3 Hybrid Indexing Strategy
- **Graph store.** Import graphs and code graphs persist as pickled NetworkX artifacts under `.local_graphs` so every agent run reuses them (`knowledge_graph/store.py:7-48`, `rag/graph_store.py:18-140`).
- **Vector store.** `rag/vector_store.index_repository` writes semantic chunks with module/risk tags; commit history and policy docs are indexed separately in `best_practices_store` and `best_practices_docs` to provide organizational priors (`best_practices_store.py:42-120`, `best_practices_docs.py:25-110`).
- **Lexical + heuristics.** `_LexicalIndex` adds BM25-style ranking of nearby files, and `_filter_by_risk` prioritizes chunks whose metadata matches manifest risk tags (`rag/reteriever.py:46-150`, `agents/context_agent.py:29-79`).
- **Gap.** There is not yet a single “Codebase Knowledge Graph” service exposing graph + vector IDs for the same entity. Linking Chroma IDs back into the graph would let agents perform mixed queries (“semantic match + graph neighborhood”).

---

## 4. System Architecture: The LangGraph Orchestrator

### 4.1 State Schema
- `ReviewState` enumerates all shared-memory fields plus private workflow controls (`workflow.py:10-27`), matching the report payload stored per commit (`workflow.py:205-231`, `review_runner.py:300-360`).

### 4.2 Supervisor Agent (Router)
- The `Supervisor` instantiates intake/triage/context/planner/synthesis/critic/memory agents, loads tool specs, and registers repo-aware RAG tools (`agents/supervisor.py:37-125`).
- It prepares per-file contexts (diff + structured context bundle) and normalizes tool findings with confidence scores and citations before they return to the graph (`agents/supervisor.py:137-395`).

### 4.3 Worker Agents
- **Cartographer analogue (partial).** `ContextAgent` merges manifest risk tags with retriever bundles, fetching import neighborhoods and memory patterns—this supplies the structural context other agents consume (`agents/context_agent.py:18-79`).
- **Sentinel analogue (partial).** `SecurityAgent` parses patches and flags heuristics like `eval`, `exec`, or `shell=True`, attaching snippets from RAG context as evidence (`agents/security_agent.py:23-52`, `tools/static_analysis.py:64-114`).
- **Stylist.** `StyleAgent` enforces length/whitespace/TODO hygiene, again tying suggested fixes to doc/best-practice citations (`agents/style_agent.py:23-54`).
- **Planner & Executor.** `PlannerAgent` decomposes work into specialist tasks/actions, while `ActionExecutor` handles “analysis” actions when no concrete tool is available (`agents/planner_agent.py:17-190`, `agents/executor_agent.py:11-67`).
- **Gap.** Dedicated agents for graph queries (“Cartographer”), taint tracing, or GraphRAG question answering are not implemented. The security agent does not yet consult multi-hop graph traversals to guarantee sanitizer coverage.

### 4.4 Synthesis and Validation Loop
- **Implemented.** `SynthesisAgent` deduplicates findings and summarizes the review, `CriticAgent` packages executive summaries and grouped comments, and `MemoryAgent` writes highlights + preference feedback to JSONL stores (`agents/synthesis_agent.py:8-54`, `agents/critic_agent.py:8-47`, `agents/memory_agent.py:8-54`).
- **Gap.** There is no explicit hallucination checker validating that every referenced file/line exists in the diff, nor a HITL interrupt node that waits for human approval before posting findings.

---

## 5. Implementation Strategy: From Code to Graph

### 5.1 Graph Builder Pipeline
- `index_repo_rag.py` provides the CI-friendly entrypoint: clone → index vectors → build import graph (`index_repo_rag.py:1-52`).
- `review_runner.run_review` orchestrates artifact refresh (vector store, import graph, code graph, best-practice docs) before LangGraph executes, then records findings + history into the knowledge-graph layers (`review_runner.py:210-360`, `knowledge_graph/findings_graph.py:10-57`, `knowledge_graph/history_graph.py:10-39`).
- **Gap.** The pipeline rebuilds full graphs on every run; there is no incremental “remove + replace file” logic or event-driven GraphRAG MCP server yet.

### 5.2 Handling Context Windows with Graph Compression
- Today the retriever limits structural scope by selecting immediate import neighbors (`RepositoryRetriever._candidate_paths`) and by trimming context chunks + lexical hits (`rag/reteriever.py:243-403`, `agents/context_agent.py:29-79`).
- **Gap.** There is no graph pruning via degree-centrality/community detection, nor automatic summarization of neighboring nodes. Injecting summarized neighbors plus importance scoring would better align with the proposed compression strategy.

### 5.3 Structured Output with Pydantic
- The system uses `TypedDict` definitions (`agents/review_types.py:4-94`) to normalize agent payloads and share contracts between nodes.
- **Gap.** No `pydantic.BaseModel` schemas or `with_structured_output` guards are in place yet, so parsing errors rely on heuristic JSON extraction (`llm_utils.extract_json_response`). Introducing actual Pydantic models per issue/report would meet the spec’s structured-output requirement.

---

## 6. Performance Analysis and Strategic Value
- **Caching + reuse.** Artifact freshness is tracked via `artifact_cache` and `ReviewSessionManager`, preventing redundant re-indexing and giving humans a cross-commit memory (`review_runner.py:210-360`, `session/session_manager.py:12-140`).
- **Telemetry.** Every LangGraph node emits progress events and LangSmith runs, enabling coarse cycle-time measurements (`workflow.py:92-204`, `telemetry/langsmith.py:10-120`).
- **Gap.** There are no benchmark scripts comparing GraphRAG vs. Vector RAG accuracy, nor automated metrics around false positives/negatives. Adding regression suites and graph-query tests would quantify the claimed >90% accuracy.

---

## 7. Future Trajectories: Self-Healing and Architectural Enforcement
1. **Graph-native query agent.** Implement a Cartographer node that converts natural-language questions into Cypher/Gremlin against the code/policy graphs, closing the determinism gap.
2. **Tree-sitter ETL.** Swap the AST-only graph builder for Tree-sitter so polyglot repos produce a uniform ontology with precise spans and `inherits` / `taints` edges.
3. **Hallucination & HITL gates.** Add a LangGraph interrupt node that validates file/line references against diffs and optionally pauses for human edits before publishing.
4. **Graph compression + summaries.** Attach importance scores, docstring summaries, and aggregated neighbor metadata to nodes so agents receive compressed, multi-hop context.
5. **Pydantic issue models.** Enforce `CodeIssue` / `ReviewReport` schemas to reduce parsing retries and make downstream filtering deterministic.
6. **Architectural rule runner.** Encode organization-specific constraints as graph queries and run them alongside security/style specialists to enable “architecture as code.”

---

## 8. Conclusion
The current Agentic Reviewer already embodies much of the proposed architecture: LangGraph handles stateful orchestration, hybrid RAG stitches together vectors with graph context, and knowledge-graph layers persist code, policy, and findings. To reach full autonomy, the roadmap must add Tree-sitter ETL, graph-query agents, hallucination checks, and structured outputs so the system can reason deterministically about every dependency ripple and enforce human-in-the-loop guardrails.

---

## Appendix: Implementation Status Snapshots

| Capability | Status | Where | Next Step |
| --- | --- | --- | --- |
| LangGraph workflow (intake → finalize) | **Implemented** | `workflow.py:10-315` | Add conditional loops + checkpointers for reflexion \& HITL pauses |
| Supervisor + specialist routing | **Implemented** | `agents/supervisor.py:37-483` | Introduce dedicated Graph Query / Sentinel agents and multi-language toolkits |
| Import + symbol graphs | **Implemented (Python-only)** | `rag/graph_store.py:55-118`, `knowledge_graph/code_graph.py:125-217` | Port to Tree-sitter, add inherits/taints edges, persist in graph DB |
| Hybrid retriever (vector + graph + lexical + policy) | **Implemented** | `rag/reteriever.py:46-403`, `agents/context_agent.py:18-79` | Provide Cypher/GraphQL interface + importance-weighted pruning |
| Security/style heuristics with RAG citations | **Implemented (heuristic)** | `agents/security_agent.py:23-52`, `agents/style_agent.py:23-54`, `tools/static_analysis.py:64-114` | Integrate taint analysis using graph traversals for sanitizer validation |
| Knowledge graph persistence (code, policy, findings, history) | **Implemented** | `knowledge_graph/*_graph.py` | Store vector IDs per node to unify semantic + structural lookups |
| Synthesis + critic + memory | **Implemented (LLM-only)** | `agents/synthesis_agent.py:8-54`, `agents/critic_agent.py:8-47`, `agents/memory_agent.py:8-54` | Add hallucination checker + structured Pydantic outputs |
| Human-in-the-loop controls | **Missing** | — | Add LangGraph interrupt nodes tied to UI/API for approval + feedback |
| Tree-sitter / polyglot parsing | **Missing** | — | Adopt Tree-sitter ETL pipeline w/ incremental updates |
| Pydantic-enforced issue schema | **Missing** | — | Introduce `CodeIssue` / `ReviewReport` models and `with_structured_output` prompts |
