"""Pydantic models for Argument Companion v3."""

from __future__ import annotations

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .anchor import Anchor

# ── Promise / Ledger ──────────────────────────────────────────────────────────

NodeKind = Literal["contribution", "claim", "hypothesis", "gap_statement", "scope"]
PromiseStatus = Literal["paid", "partial", "unpaid", "mismatch", "unknown"]


class Promise(BaseModel):
    id: str = Field(default_factory=lambda: f"p_{uuid.uuid4().hex[:10]}")
    text: str
    kind: NodeKind
    source_anchor_id: str
    discharge_anchor_ids: list[str] = Field(default_factory=list)
    status: PromiseStatus = "unknown"
    severity: Literal["info", "warning", "error"] = "info"
    note: Optional[str] = None
    created_by: Literal["user", "ai"] = "ai"
    user_overridden: bool = False


class Ledger(BaseModel):
    id: str = Field(default_factory=lambda: f"L_{uuid.uuid4().hex[:10]}")
    doc_id: str
    doc_title: str = ""
    promises: list[Promise] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    doc_hash: Optional[str] = None
    last_built_at: float = Field(default_factory=time.time)


# ── ReviewPoint / ReviewSession ───────────────────────────────────────────────

PointSeverity = Literal["minor", "major", "fatal"]
PointCategory = Literal[
    "motivation", "novelty", "baseline", "ablation", "soundness",
    "claim_overreach", "missing_related_work", "reproducibility",
    "experiment_design", "writing_clarity",
    "inconsistency",
    "gap_mismatch",
    "weak_positioning",
    "term_drift",
    "other",
]
PointStatus = Literal["open", "rebutted", "accepted", "dismissed"]
PointSource = Literal[
    "llm",
    "ledger_check",
    "coherence_check",
    "rw_check",
    "scoped",
    "imported",
]


class RebuttalTurn(BaseModel):
    id: str = Field(default_factory=lambda: f"rt_{uuid.uuid4().hex[:10]}")
    role: Literal["author", "reviewer"]
    text: str
    created_at: float = Field(default_factory=time.time)


class ReviewPoint(BaseModel):
    id: str = Field(default_factory=lambda: f"rp_{uuid.uuid4().hex[:10]}")
    severity: PointSeverity
    category: PointCategory
    title: str
    detail: str
    anchor_id: Optional[str] = None
    status: PointStatus = "open"
    source: PointSource = "llm"
    reviewer_label: Optional[str] = None
    perspective: Optional[Literal["method", "experiment", "writing", "aggregated"]] = None
    thread: list[RebuttalTurn] = Field(default_factory=list)


class ReviewSession(BaseModel):
    id: str = Field(default_factory=lambda: f"R_{uuid.uuid4().hex[:10]}")
    doc_id: str
    doc_title: str = ""
    venue: Optional[str] = None
    persona: Literal["reviewer2", "ac", "domain_expert", "friendly", "real"] = "reviewer2"
    checks: list[str] = Field(default_factory=lambda: ["llm"])
    points: list[ReviewPoint] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    doc_hash: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
