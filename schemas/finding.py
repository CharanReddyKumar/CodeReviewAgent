from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    type: Literal["code_span", "tool_output", "policy_quote"]
    file: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
    sha: Optional[str] = None
    tool_id: Optional[str] = None
    issue_id: Optional[str] = None
    message: Optional[str] = None
    doc_id: Optional[str] = None
    text: Optional[str] = None


class Finding(BaseModel):
    title: str
    severity: Literal["blocker", "high", "medium", "low", "nit"]
    file: str
    line_start: int
    line_end: int
    category: Literal["security", "correctness", "performance", "style", "docs", "tests"]
    description: str
    suggested_patch: Optional[str] = None
    evidence: List[Evidence] = Field(min_items=1)
    references: Optional[List[str]] = None
