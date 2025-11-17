# Graph Visualization Playground

This lightweight helper lets you inspect the reviewer graphs (code structure, history, policy, or import graph) without leaving your machine.

## Usage

1. Install dependencies (FastAPI + Uvicorn already exist for the API):

   ```bash
   uvicorn graph_viz.server:app --reload --port 9000
   ```

2. Open your browser to `http://127.0.0.1:9000`. Enter the repository reference (`github.com/owner/repo`) and pick a layer:

   - `code`: function/class/file relationships from `knowledge_graph`
   - `history`: commit-level graph (if available)
   - `policy`: docs/policy topics graph
   - `import`: module import graph (`rag.graph_store`)

3. Click **Load Graph** to fetch `/graph-data?repo=...&layer=...` and render the force-directed view. Hover nodes to see labels; drag nodes to reorganize the layout.

The FastAPI endpoint reuses the pickled graphs already built by the reviewer, so there is no extra ingestion step.
