"""Toulmin 论证图 v2 数据模型。"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal["claim", "grounds", "warrant", "backing", "qualifier", "rebuttal"]

RelationType = Literal[
    "supports",  # grounds  -> claim
    "warrants",  # warrant  -> claim
    "backs",  # backing  -> warrant
    "qualifies",  # qualifier-> claim
    "rebuts",  # rebuttal -> claim
    "counters",  # claim/grounds -> rebuttal
]

# (source_node_type, target_node_type) pairs allowed per relation
ALLOWED_EDGES: dict[str, set[tuple[str, str]]] = {
    "supports": {("grounds", "claim")},
    "warrants": {("warrant", "claim")},
    "backs": {("backing", "warrant")},
    "qualifies": {("qualifier", "claim")},
    "rebuts": {("rebuttal", "claim")},
    "counters": {("claim", "rebuttal"), ("grounds", "rebuttal")},
}


class SpanMapping(BaseModel):
    id: str = Field(default_factory=lambda: f"sp_{uuid.uuid4().hex[:10]}")
    node_id: str
    source_type: Literal["block", "selection", "editor", "extracted"]
    block_id: str | None = None
    side: Literal["orig", "trans"] = "trans"
    char_start: int | None = None
    char_end: int | None = None
    quote: str
    source_label: str | None = None


class ArgIssue(BaseModel):
    id: str = Field(default_factory=lambda: f"is_{uuid.uuid4().hex[:10]}")
    node_id: str | None = None
    edge_id: str | None = None
    severity: Literal["info", "warning", "error"]
    category: Literal[
        "missing_grounds",
        "missing_warrant",
        "missing_backing",
        "unaddressed_rebuttal",
        "fallacy",
        "weak_link",
        "orphan",
        "unsupported_qualifier",
        "other",
    ]
    message: str
    suggestion: str | None = None


class ArgNode(BaseModel):
    id: str = Field(default_factory=lambda: f"n_{uuid.uuid4().hex[:10]}")
    node_type: NodeType
    text: str
    label: str | None = None
    confidence: float | None = None
    position: dict | None = None
    span_ids: list[str] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list)
    created_by: Literal["user", "ai"] = "user"


class ArgEdge(BaseModel):
    id: str = Field(default_factory=lambda: f"e_{uuid.uuid4().hex[:10]}")
    source_id: str
    target_id: str
    relation_type: RelationType
    label: str | None = None
    created_by: Literal["user", "ai"] = "user"


class ArgGraph(BaseModel):
    id: str = Field(default_factory=lambda: f"g_{uuid.uuid4().hex[:10]}")
    title: str = "Untitled Argument Map"
    nodes: list[ArgNode] = Field(default_factory=list)
    edges: list[ArgEdge] = Field(default_factory=list)
    spans: list[SpanMapping] = Field(default_factory=list)
    issues: list[ArgIssue] = Field(default_factory=list)
    source_doc: str | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
