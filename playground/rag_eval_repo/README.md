# RAG Evaluation Mini-Repo

This synthetic repository exercises the CodeReviewAgent RAG pipeline. It contains:

- A tiny analytics service that exposes a `TrendAnalyzer` for correlating sensor data.
- A vector math helper with intentionally descriptive docstrings for retrieval tests.
- Narrative docs explaining the forecasting assumptions.
- Unit tests that import production modules (to validate the import graph / graph-RAG pathing).

Use this repo when running `rag.vector_store.index_repository` and `rag.graph_store.build_import_graph` to generate embeddings + graph artifacts for local QA.
