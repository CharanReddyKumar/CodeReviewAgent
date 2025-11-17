from langsmith import Client
import json

# Your root run ID
ROOT_RUN_ID = "1c01f57d-54c8-4367-907f-54cc78fdd90e"
OUT_PATH = "agentic-review-trace.jsonl"


def export_trace(root_run_id: str, out_path: str) -> None:
    client = Client()  # uses LANGSMITH_API_KEY / LANGSMITH_PROJECT from env

    # 1) Read the root run
    root = client.read_run(root_run_id)

    # 2) Get ALL runs in that trace (root + children)
    runs = list(
        client.list_runs(
            trace_id=root.trace_id,
            # don't pass project_name; older clients don't need it
        )
    )

    # 3) Sort by start time (if present) for readability
    runs.sort(key=lambda r: getattr(r, "start_time", None) or 0)

    # 4) Dump each run as a JSON line
    with open(out_path, "w", encoding="utf-8") as f:
        for r in runs:
            # Support both new and old client versions:
            if hasattr(r, "model_dump_json"):
                # Newer pydantic v2-style
                line = r.model_dump_json()
            elif hasattr(r, "json"):
                # Older pydantic v1-style
                line = r.json()
            else:
                # Fallback: try dict() + json.dumps
                data = r.dict() if hasattr(r, "dict") else r.__dict__
                line = json.dumps(data, default=str)
            f.write(line + "\n")

    print(f"Exported {len(runs)} runs to {out_path}")


if __name__ == "__main__":
    export_trace(ROOT_RUN_ID, OUT_PATH)
