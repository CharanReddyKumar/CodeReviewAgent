from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from review_runner import run_review
from dotenv import load_dotenv
load_dotenv()


class ReviewRequest(BaseModel):
    repo: str = Field(..., description="Repository URL or local path")
    branch: str = Field("main", description="Git branch or ref to inspect")
    max_commits: int = Field(1, ge=1, le=10)
    refresh_artifacts: bool = False
    refresh_best_practices: bool = False
    best_practices_docs: Optional[str] = Field(
        None, description="Optional path to a folder of best-practices documents"
    )
    force_artifacts: bool = False
    pr: Optional[int] = Field(None, description="Optional pull-request number")
    base: Optional[str] = Field(None, description="Optional base ref for diffing")


class ReviewResponse(BaseModel):
    runs: List[Dict[str, Any]]


app = FastAPI(title="Agentic Reviewer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/review", response_model=ReviewResponse)
def review_repo(payload: ReviewRequest) -> ReviewResponse:
    try:
        results = run_review(
            payload.repo,
            payload.branch,
            max_commits=payload.max_commits,
            refresh_artifacts=payload.refresh_artifacts,
            refresh_best_practices=payload.refresh_best_practices,
            best_practices_docs=Path(payload.best_practices_docs) if payload.best_practices_docs else None,
            force_artifacts=payload.force_artifacts,
            pr=payload.pr,
            base=payload.base,
        )
    except Exception as exc:  # pragma: no cover - surface errors to client
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ReviewResponse(runs=results)


@app.get("/review/stream")
async def review_stream(
    repo: str,
    branch: str = "main",
    max_commits: int = 1,
) -> StreamingResponse:
    queue: asyncio.Queue[tuple[Optional[str], Optional[Dict[str, Any]]]] = asyncio.Queue()

    loop = asyncio.get_event_loop()

    def progress(event: str, data: Dict[str, Any]) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (event, data))
        except RuntimeError:
            pass

    async def worker():
        try:
            results = await asyncio.to_thread(
                run_review,
                repo,
                branch,
                max_commits=max_commits,
                progress_callback=progress,
            )
            await queue.put(("complete", {"runs": results}))
        except Exception as exc:
            await queue.put(("error", {"detail": str(exc)}))
        finally:
            await queue.put((None, None))

    async def event_generator():
        worker_task = asyncio.create_task(worker())
        try:
            while True:
                event, data = await queue.get()
                if event is None:
                    break
                payload = json.dumps(data or {})
                yield f"event: {event}\ndata: {payload}\n\n"
        finally:
            await worker_task

    return StreamingResponse(event_generator(), media_type="text/event-stream")
