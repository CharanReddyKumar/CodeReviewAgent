from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict


class ReviewManifest(TypedDict, total=False):
    summary: str
    files: List[str]
    languages: List[str]
    components: List[str]
    high_risk_tags: List[str]
    size: Literal["tiny", "small", "medium", "large", "mega"]
    priority: Literal["low", "medium", "high", "urgent"]
    description: str
    frameworks: List[str]


class ContextPacket(TypedDict, total=False):
    id: str
    file_path: str
    module: str
    description: str
    neighbors: List[str]
    tests: List[str]
    configs: List[str]
    docs: List[str]
    history: List[Dict[str, Any]]
    rag_code: List[Dict[str, Any]]
    rag_docs: List[Dict[str, Any]]
    rag_best_practices: List[Dict[str, Any]]
    rag_policy: List[Dict[str, Any]]
    import_context: List[Dict[str, Any]]
    patch: str
    symbol_context: List[Dict[str, Any]]
    lexical_context: List[Dict[str, Any]]
    memory_patterns: List[Dict[str, Any]]


class TriageDecision(TypedDict, total=False):
    file_path: str
    risk: Literal["low", "medium", "high"]
    file_type: str
    lanes: List[str]
    notes: str


class TriagePlan(TypedDict, total=False):
    overall_risk: Literal["low", "medium", "high"]
    lanes: List[str]
    decisions: List[TriageDecision]
    recommendations: List[str]


class PlannerTask(TypedDict, total=False):
    id: str
    title: str
    specialist: str
    files: List[str]
    priority: Literal["low", "medium", "high", "urgent"]
    budget: Literal["xs", "s", "m", "l"]
    notes: str
    risks: List[str]
    context_ids: List[str]
    tool_ids: List[str]
    actions: List["TaskAction"]


class TaskAction(TypedDict, total=False):
    type: Literal["analysis", "tool", "note"]
    description: str
    instructions: str
    tool_ids: List[str]
    files: List[str]


class TaskActionResult(TypedDict, total=False):
    type: str
    description: str
    output: str
    tool_ids: List[str]
    files: List[str]
    findings: int


class SpecialistFinding(TypedDict, total=False):
    agent: str
    file_path: str
    span: str
    severity: Literal["blocker", "high", "medium", "low", "info"]
    category: str
    message: str
    recommended_fix: str
    references: Dict[str, str]
    code_line: str
    rule_id: str
    confidence: Literal["low", "medium", "high"]
    citations: List[str]


class TaskReport(TypedDict, total=False):
    task_id: str
    title: str
    tool_ids: List[str]
    findings: List[SpecialistFinding]
    notes: str
    action_results: List[TaskActionResult]


class SynthesisOutput(TypedDict, total=False):
    normalized_findings: List[SpecialistFinding]
    summary: str


class CriticOutput(TypedDict, total=False):
    executive_summary: str
    grouped_comments: List[Dict[str, Any]]
    follow_ups: List[str]
