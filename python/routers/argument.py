"""Argument Mapping routes — Toulmin v2 graph (sole implementation)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)


# ── v2 request body models (module-level so FastAPI can resolve annotations) ─

class V2CreateGraphRequest(BaseModel):
    title: str = "未命名论证图"
    source_doc: str | None = None


# ── companion v3 request body models (module-level for FastAPI annotation resolution) ─

class CompanionBuildLedgerRequest(BaseModel):
    doc_id: str
    doc_title: str = ""
    text: str


class CompanionRelocateRequest(BaseModel):
    text: str


class CompanionPromiseUpsertRequest(BaseModel):
    id: str | None = None
    text: str
    kind: str
    source_anchor_id: str
    discharge_anchor_ids: list[str] = []
    status: str = "unknown"
    note: str | None = None


class CompanionReviewRequest(BaseModel):
    doc_id: str
    doc_title: str = ""
    text: str
    venue: str | None = None
    persona: str = "reviewer2"
    focus: str | dict | None = None
    checks: list[str] | None = None
    session_id: str | None = None


class CompanionUpdatePointRequest(BaseModel):
    status: str


class CompanionRebutRequest(BaseModel):
    message: str
    text: str = ""


class CompanionImportReviewsRequest(BaseModel):
    doc_id: str
    doc_title: str = ""
    text: str
    reviews_raw: str


# v2 models imported eagerly at module level so that `from __future__ import
# annotations` string-annotation resolution finds them in module globals.
try:
    from src.argument.models_v2 import ArgNode, ArgEdge, SpanMapping  # noqa: F401
    _V2_MODELS_AVAILABLE = True
except ImportError:
    _V2_MODELS_AVAILABLE = False


# ── Toulmin v2 端点 ──────────────────────────────────────────────────────────


def register_argument_v2(
    app: FastAPI,
    *,
    store,  # ArgGraphStore instance
    flag_enabled: bool = False,
    load_config=None,
    build_cloud_client=None,
    runtime_dir: Path | None = None,
) -> None:
    """注册 Toulmin 论证图 v2 CRUD + AI 端点。

    仅当 flag_enabled=True 时注册；否则所有 /api/argument/* v2 路径返回 404。
    与旧树端点并存，不冲突。
    """
    if not flag_enabled:
        return

    def _get_cloud_client():
        if load_config is None or build_cloud_client is None:
            return None
        config = load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        if not cloud_cfg.get("api_key"):
            return None
        return build_cloud_client(trans_cfg, cloud_cfg)

    @app.get("/api/argument/graphs")
    def v2_list_graphs():
        return store.list_graphs()

    @app.post("/api/argument/graph")
    def v2_create_graph(req: V2CreateGraphRequest):
        g = store.create(title=req.title, source_doc=req.source_doc)
        return g.model_dump()

    @app.get("/api/argument/graph/{gid}")
    def v2_get_graph(gid: str):
        g = store.get(gid)
        if g is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        return g.model_dump()

    @app.delete("/api/argument/graph/{gid}")
    def v2_delete_graph(gid: str):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        store.delete(gid)
        return {"ok": True}

    @app.put("/api/argument/graph/{gid}/node")
    def v2_upsert_node(gid: str, req: ArgNode):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        node = store.upsert_node(gid, req)
        return node.model_dump()

    @app.delete("/api/argument/graph/{gid}/node/{nid}")
    def v2_delete_node(gid: str, nid: str):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        try:
            store.delete_node(gid, nid)
        except KeyError:
            raise HTTPException(status_code=404, detail="Node not found")
        return {"ok": True}

    @app.put("/api/argument/graph/{gid}/edge")
    def v2_upsert_edge(gid: str, req: ArgEdge):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        try:
            edge = store.upsert_edge(gid, req)
        except ValueError as exc:
            msg = str(exc)
            if "invalid_edge" in msg or "self_loop" in msg or "self loop" in msg or "duplicate" in msg:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_edge", "detail": msg},
                )
            raise HTTPException(status_code=400, detail=msg)
        return edge.model_dump()

    @app.delete("/api/argument/graph/{gid}/edge/{eid}")
    def v2_delete_edge(gid: str, eid: str):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        store.delete_edge(gid, eid)
        return {"ok": True}

    @app.put("/api/argument/graph/{gid}/span")
    def v2_add_span(gid: str, req: SpanMapping):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        span = store.add_span(gid, req)
        return span.model_dump()

    @app.delete("/api/argument/graph/{gid}/span/{sid}")
    def v2_delete_span(gid: str, sid: str):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        store.delete_span(gid, sid)
        return {"ok": True}

    # ── AI 端点 ─────────────────────────────────────────────────────────────

    class ExtractRequest(BaseModel):
        text: str
        source_label: str | None = None
        side: str = "trans"

    class CritiqueRequest(BaseModel):
        pass  # currently whole-graph critique only

    class SuggestRequest(BaseModel):
        node_id: str

    @app.post("/api/argument/graph/{gid}/extract")
    async def v2_extract(gid: str, req: ExtractRequest):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        from src.argument.ai_ops import extract_argument

        cloud_client = _get_cloud_client()

        async def _gen():
            async for ev in extract_argument(
                gid=gid,
                text=req.text,
                source_label=req.source_label,
                side=req.side,
                store=store,
                cloud_client=cloud_client,
            ):
                yield {"event": ev["event"], "data": ev["data"]}

        return EventSourceResponse(_gen())

    @app.post("/api/argument/graph/{gid}/critique")
    async def v2_critique(gid: str):
        g = store.get(gid)
        if g is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        from src.argument.critique import critique_graph

        cloud_client = _get_cloud_client()
        issues = await critique_graph(g, cloud_client=cloud_client)
        store.set_issues(gid, issues)
        return {"issues": [i.model_dump() for i in issues]}

    @app.post("/api/argument/graph/{gid}/suggest")
    async def v2_suggest(gid: str, req: SuggestRequest):
        if store.get(gid) is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        from src.argument.ai_ops import suggest_element

        cloud_client = _get_cloud_client()
        result = await suggest_element(
            graph_id=gid,
            node_id=req.node_id,
            store=store,
            cloud_client=cloud_client,
        )
        return result

    # ── Flatten 端点（图→草稿） ─────────────────────────────────────────────

    _flatten_tasks_v2: dict[str, dict] = {}
    _flatten_output_dir_v2 = (runtime_dir / "argument_output_v2") if runtime_dir else Path("argument_output_v2")
    _flatten_output_dir_v2.mkdir(parents=True, exist_ok=True)

    class FlattenGraphRequest(BaseModel):
        template: str = "markdown"
        title: str = ""

    @app.post("/api/argument/graph/{gid}/flatten")
    async def v2_flatten(gid: str, req: FlattenGraphRequest):
        g = store.get(gid)
        if g is None:
            raise HTTPException(status_code=404, detail="Graph not found")

        task_id = f"fv2_{uuid.uuid4().hex[:8]}"
        _flatten_tasks_v2[task_id] = {"status": "pending", "output_path": ""}

        from src.argument.flatten_graph import flatten_graph_stream

        async def _gen():
            _flatten_tasks_v2[task_id]["status"] = "processing"
            try:
                async for ev in flatten_graph_stream(
                    graph=g,
                    template=req.template,
                    title=req.title or g.title,
                    output_dir=_flatten_output_dir_v2,
                ):
                    if ev.get("event") == "complete":
                        data = json.loads(ev.get("data", "{}"))
                        _flatten_tasks_v2[task_id]["output_path"] = data.get("output_path", "")
                        _flatten_tasks_v2[task_id]["status"] = "done"
                    yield {"event": ev["event"], "data": ev["data"]}
            except Exception as exc:
                _flatten_tasks_v2[task_id]["status"] = "error"
                yield {"event": "error", "data": json.dumps({"message": str(exc)})}

        return EventSourceResponse(_gen())

    @app.get("/api/argument/flatten_v2/{task_id}/download")
    def v2_flatten_download(task_id: str):
        task = _flatten_tasks_v2.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] != "done":
            raise HTTPException(status_code=400, detail="Task not completed")
        op = Path(task["output_path"])
        if not op.exists():
            raise HTTPException(status_code=404, detail="Output file not found")
        ct_map = {".md": "text/markdown", ".tex": "text/x-latex"}
        ct = ct_map.get(op.suffix, "text/plain")
        return FileResponse(op, media_type=ct, filename=op.name)


# ── Argument Companion v3 端点 ────────────────────────────────────────────────


def register_companion(
    app: FastAPI,
    *,
    store,  # CompanionStore instance
    flag_enabled: bool = False,
    load_config=None,
    build_cloud_client=None,
) -> None:
    """注册 Argument Companion v3 端点（/api/companion/*）。

    仅当 flag_enabled=True 时注册；否则路径返回 404。
    与 register_argument_v2 并存，不冲突。
    """
    if not flag_enabled:
        return

    def _get_cloud_client():
        if load_config is None or build_cloud_client is None:
            return None
        config = load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        if not cloud_cfg.get("api_key"):
            return None
        return build_cloud_client(trans_cfg, cloud_cfg)

    # ── Ledger endpoints ───────────────────────────────────────────────────

    @app.post("/api/companion/ledger/build")
    async def companion_build_ledger(req: CompanionBuildLedgerRequest):
        from src.argument.ledger import build_ledger, rebuild_ledger

        cloud_client = _get_cloud_client()
        fn = rebuild_ledger if store.get_ledger(req.doc_id) else build_ledger

        async def _gen():
            async for ev in fn(
                doc_id=req.doc_id,
                doc_title=req.doc_title,
                text=req.text,
                store=store,
                cloud_client=cloud_client,
            ):
                yield {"event": ev["event"], "data": ev["data"]}

        return EventSourceResponse(_gen())

    @app.get("/api/companion/ledger/{doc_id}")
    def companion_get_ledger(doc_id: str):
        ledger = store.get_ledger(doc_id)
        if ledger is None:
            raise HTTPException(status_code=404, detail="Ledger not found")
        return ledger.model_dump()

    @app.put("/api/companion/ledger/{doc_id}/promise")
    def companion_upsert_promise(doc_id: str, req: CompanionPromiseUpsertRequest):
        from src.argument.companion_models import Promise
        ledger = store.get_ledger(doc_id)
        if ledger is None:
            raise HTTPException(status_code=404, detail="Ledger not found")
        kwargs = dict(
            text=req.text,
            kind=req.kind,
            source_anchor_id=req.source_anchor_id,
            discharge_anchor_ids=req.discharge_anchor_ids,
            status=req.status,
            note=req.note,
            created_by="user",
            user_overridden=True,
        )
        if req.id:
            kwargs["id"] = req.id
        p = Promise(**kwargs)  # type: ignore[arg-type]
        store.upsert_promise(doc_id, p)
        return p.model_dump()

    @app.delete("/api/companion/ledger/{doc_id}/promise/{pid}")
    def companion_delete_promise(doc_id: str, pid: str):
        if store.get_ledger(doc_id) is None:
            raise HTTPException(status_code=404, detail="Ledger not found")
        store.delete_promise(doc_id, pid)
        return {"ok": True}

    @app.post("/api/companion/ledger/{doc_id}/relocate")
    def companion_relocate(doc_id: str, req: CompanionRelocateRequest):
        from src.argument.anchor import relocate_all
        import hashlib
        ledger = store.get_ledger(doc_id)
        if ledger is None:
            raise HTTPException(status_code=404, detail="Ledger not found")
        ledger.anchors = relocate_all(ledger.anchors, req.text)
        ledger.doc_hash = hashlib.sha1(req.text.encode()).hexdigest()[:16]
        store.save_ledger(ledger)
        return ledger.model_dump()

    @app.delete("/api/companion/ledger/{doc_id}")
    def companion_delete_ledger(doc_id: str):
        if store.get_ledger(doc_id) is None:
            raise HTTPException(status_code=404, detail="Ledger not found")
        store.delete_ledger(doc_id)
        return {"ok": True}

    # ── Review endpoints ───────────────────────────────────────────────────

    @app.post("/api/companion/review")
    async def companion_review(req: CompanionReviewRequest):
        from src.argument.reviewer import run_review

        cloud_client = _get_cloud_client()
        ledger = store.get_ledger(req.doc_id)

        async def _gen():
            async for ev in run_review(
                doc_id=req.doc_id,
                doc_title=req.doc_title,
                text=req.text,
                venue=req.venue,
                persona=req.persona,
                ledger=ledger,
                store=store,
                focus=req.focus,
                checks=req.checks,
                session_id=req.session_id,
                cloud_client=cloud_client,
            ):
                yield {"event": ev["event"], "data": ev["data"]}

        return EventSourceResponse(_gen())

    @app.get("/api/companion/review/{session_id}")
    def companion_get_review(session_id: str):
        s = store.get_review(session_id)
        if s is None:
            raise HTTPException(status_code=404, detail="Review session not found")
        return s.model_dump()

    @app.get("/api/companion/reviews")
    def companion_list_reviews(doc_id: str):
        return store.list_reviews(doc_id)

    @app.put("/api/companion/review/{session_id}/point/{pid}")
    def companion_update_point(session_id: str, pid: str, req: CompanionUpdatePointRequest):
        # Validate status value
        valid_statuses = {"open", "rebutted", "accepted", "dismissed"}
        if req.status not in valid_statuses:
            raise HTTPException(status_code=422, detail=f"Invalid status: {req.status!r}")
        s = store.get_review(session_id)
        if s is None:
            raise HTTPException(status_code=404, detail="Review session not found")
        try:
            store.update_point(session_id, pid, req.status)
        except KeyError:
            raise HTTPException(status_code=404, detail="Point not found")
        return {"ok": True}

    @app.post("/api/companion/review/{session_id}/point/{pid}/rebut")
    async def companion_rebut(session_id: str, pid: str, req: CompanionRebutRequest):
        from src.argument.reviewer import continue_rebuttal

        cloud_client = _get_cloud_client()
        s = store.get_review(session_id)
        if s is None:
            raise HTTPException(status_code=404, detail="Review session not found")

        async def _gen():
            async for ev in continue_rebuttal(
                session_id=session_id,
                point_id=pid,
                author_message=req.message,
                doc_text=req.text,
                store=store,
                cloud_client=cloud_client,
            ):
                yield {"event": ev["event"], "data": ev["data"]}

        return EventSourceResponse(_gen())

    @app.delete("/api/companion/review/{session_id}")
    def companion_delete_review(session_id: str):
        if store.get_review(session_id) is None:
            raise HTTPException(status_code=404, detail="Review session not found")
        store.delete_review(session_id)
        return {"ok": True}

    # ── Phase 5 endpoints ─────────────────────────────────────────────────────

    @app.post("/api/companion/review/import")
    async def companion_import_reviews(req: CompanionImportReviewsRequest):
        from src.argument.reviewer import import_real_reviews

        cloud_client = _get_cloud_client()

        async def _gen():
            async for ev in import_real_reviews(
                doc_id=req.doc_id,
                doc_title=req.doc_title,
                text=req.text,
                reviews_raw=req.reviews_raw,
                store=store,
                cloud_client=cloud_client,
            ):
                yield {"event": ev["event"], "data": ev["data"]}

        return EventSourceResponse(_gen())

    @app.get("/api/companion/download/review/{session_id}")
    def companion_download_review(session_id: str):
        session = store.get_review(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Review session not found")

        lines: list[str] = [
            f"# Rebuttal Draft — {session.doc_title or session.doc_id}",
            f"Session: {session.id}  |  Persona: {session.persona}",
            "",
        ]
        for point in session.points:
            label = f" [{point.reviewer_label}]" if point.reviewer_label else ""
            lines.append(f"## [{point.severity.upper()}]{label} {point.title}")
            lines.append(f"*Category: {point.category} · Status: {point.status}*")
            lines.append("")
            lines.append(point.detail)
            if point.thread:
                lines.append("")
                lines.append("### Discussion")
                for turn in point.thread:
                    role_label = "**Author**" if turn.role == "author" else "**Reviewer**"
                    lines.append(f"{role_label}: {turn.text}")
            lines.append("")
            lines.append("---")
            lines.append("")

        content = "\n".join(lines)
        tmp = Path("/tmp") if Path("/tmp").exists() else Path(".")
        out_file = tmp / f"rebuttal_{session_id[:8]}.md"
        out_file.write_text(content, encoding="utf-8")
        return FileResponse(
            str(out_file),
            media_type="text/markdown",
            filename=f"rebuttal_{session.doc_title or session_id[:8]}.md",
        )

    @app.post("/api/companion/ledger/{doc_id}/promise/{pid}/suggest-experiment")
    async def companion_suggest_experiment(doc_id: str, pid: str):
        from src.argument.ledger import suggest_experiment_for_promise

        ledger = store.get_ledger(doc_id)
        if ledger is None:
            raise HTTPException(status_code=404, detail="Ledger not found")
        promise = next((p for p in ledger.promises if p.id == pid), None)
        if promise is None:
            raise HTTPException(status_code=404, detail="Promise not found")

        cloud_client = _get_cloud_client()
        suggestion = await suggest_experiment_for_promise(
            promise_text=promise.text,
            promise_note=promise.note,
            cloud_client=cloud_client,
        )
        return {"suggestion": suggestion}
