"""Argument Mapping — Pydantic 数据模型"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str = "node") -> str:
    import secrets
    return f"{prefix}_{secrets.token_hex(2)}"


# ── Enums ──────────────────────────────────────────────────────────────

class LogicStatus(str, Enum):
    pass_ = "pass"
    warning = "warning"
    error = "error"


class NodeStatus(str, Enum):
    draft = "draft"
    expanded = "expanded"
    final = "final"


class BindingType(str, Enum):
    auto_suggested = "auto_suggested"
    user_manual = "user_manual"


class IssueSeverity(str, Enum):
    warning = "warning"
    error = "error"


# ── Data Models ────────────────────────────────────────────────────────

class Reference(BaseModel):
    doc_id: str
    citation_key: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    binding_type: BindingType
    bound_at: str = Field(default_factory=_now_iso)


class ArgumentNode(BaseModel):
    id: str = Field(default_factory=lambda: _gen_id("node"))
    parent_id: str | None = None
    topic: str
    content: str = ""
    depth: int = 0
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    domain_tags: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    logic_status: LogicStatus = LogicStatus.warning
    rule_issues: list[str] = Field(default_factory=list)
    agent_feedback: str | None = None
    status: NodeStatus = NodeStatus.draft
    children: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class ArgumentTree(BaseModel):
    root_id: str | None = None
    nodes: dict[str, ArgumentNode] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class RuleIssue(BaseModel):
    issue_code: str
    severity: IssueSeverity = IssueSeverity.warning
    node_ids: list[str] = Field(default_factory=list)
    related_nodes: list[str] = Field(default_factory=list)
    description: str = ""
    suggestion: str = ""
    template: str | None = None


# ── API Request/Response schemas ───────────────────────────────────────

class CreateTreeRequest(BaseModel):
    topic: str
    domain_tags: list[str] = Field(default_factory=list)
    position: dict[str, float] | None = None


class UpsertNodeRequest(BaseModel):
    id: str | None = None
    parent_id: str | None = None
    topic: str | None = None
    content: str | None = None
    domain_tags: list[str] | None = None
    position: dict[str, float] | None = None
    status: NodeStatus | None = None


class ExpandRequest(BaseModel):
    node_id: str
    max_children: int = 4
    direction: str = "expand"


class ObserveRequest(BaseModel):
    node_id: str
    content_hint: str | None = None


class BindRequest(BaseModel):
    node_id: str
    doc_id: str
    binding_type: BindingType = BindingType.user_manual
    relevance_score: float = 0.0


class ReviewRequest(BaseModel):
    node_id: str
    include_subtree: bool = True


class FlattenRequest(BaseModel):
    node_id: str = "root"
    template: str = "markdown"
    include_references: bool = True
    style: str = "IEEE"


class RecommendationItem(BaseModel):
    doc_id: str
    citation_key: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    relevance_score: float = 0.0
    excerpt: str = ""
    match_type: str = "keyword"
