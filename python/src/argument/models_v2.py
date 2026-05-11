"""Toulmin 论证图 v2 数据模型。"""

from __future__ import annotations

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

NodeType = Literal["claim", "grounds", "warrant", "backing", "qualifier", "rebuttal"]

RelationType = Literal[
    "supports",   # grounds  -> claim
    "warrants",   # warrant  -> claim
    "backs",      # backing  -> warrant
    "qualifies",  # qualifier-> claim
    "rebuts",     # rebuttal -> claim
    "counters",   # claim/grounds -> rebuttal
]

# (source_node_type, target_node_type) pairs allowed per relation
ALLOWED_EDGES: dict[str, set[tuple[str, str]]] = {
    "supports":  {("grounds", "claim")},
    "warrants":  {("warrant", "claim")},
    "backs":     {("backing", "warrant")},
    "qualifies": {("qualifier", "claim")},
    "rebuts":    {("rebuttal", "claim")},
    "counters":  {("claim", "rebuttal"), ("grounds", "rebuttal")},
}


class SpanMapping(BaseModel):
    id: str = Field(default_factory=lambda: f"sp_{uuid.uuid4().hex[:10]}")
    node_id: str
    source_type: Literal["block", "selection", "editor", "extracted"]
    block_id: Optional[str] = None
    side: Literal["orig", "trans"] = "trans"
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    quote: str
    source_label: Optional[str] = None


class ArgIssue(BaseModel):
    id: str = Field(default_factory=lambda: f"is_{uuid.uuid4().hex[:10]}")
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    severity: Literal["info", "warning", "error"]
    category: Literal[
        "missing_grounds", "missing_warrant", "missing_backing",
        "unaddressed_rebuttal", "fallacy", "weak_link", "orphan",
        "unsupported_qualifier", "other",
    ]
    message: str
    suggestion: Optional[str] = None


class ArgNode(BaseModel):
    id: str = Field(default_factory=lambda: f"n_{uuid.uuid4().hex[:10]}")
    node_type: NodeType
    text: str
    label: Optional[str] = None
    confidence: Optional[float] = None
    position: Optional[dict] = None
    span_ids: list[str] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list)
    created_by: Literal["user", "ai"] = "user"


class ArgEdge(BaseModel):
    id: str = Field(default_factory=lambda: f"e_{uuid.uuid4().hex[:10]}")
    source_id: str
    target_id: str
    relation_type: RelationType
    label: Optional[str] = None
    created_by: Literal["user", "ai"] = "user"


class ArgGraph(BaseModel):
    id: str = Field(default_factory=lambda: f"g_{uuid.uuid4().hex[:10]}")
    title: str = "未命名论证图"
    nodes: list[ArgNode] = Field(default_factory=list)
    edges: list[ArgEdge] = Field(default_factory=list)
    spans: list[SpanMapping] = Field(default_factory=list)
    issues: list[ArgIssue] = Field(default_factory=list)
    source_doc: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
