from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    highlight: int = 0


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str


class GraphPayload(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class QueryPayload(BaseModel):
    sql: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    mode: str = "template"


class ChatResponse(BaseModel):
    answer: str
    guardrail_blocked: bool = False
    query: QueryPayload = Field(default_factory=QueryPayload)
    graph: GraphPayload = Field(default_factory=GraphPayload)
    suggestions: list[str] = Field(default_factory=list)
