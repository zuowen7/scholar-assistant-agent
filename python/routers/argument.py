"""Argument Mapping routes — simple fallback + advanced (when argument module available)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)


class ArgumentTreeCreateRequest(BaseModel):
    topic: str
    domain_tags: list[str] = []
    position: dict | None = None


class ArgumentNodeRequest(BaseModel):
    id: str | None = None
    topic: str
    parent_id: str | None = None
    content: str = ""
    domain_tags: list[str] = []
    position: dict | None = None


class ArgumentExpandRequest(BaseModel):
    node_id: str
    max_children: int = 4
    direction: str = "expand"


class ArgumentObserveRequest(BaseModel):
    node_id: str
    content_hint: str = ""


class ArgumentBindRequest(BaseModel):
    node_id: str
    doc_id: str
    binding_type: str = "user_manual"
    relevance_score: float = 0.0


class ArgumentReviewRequest(BaseModel):
    node_id: str = "root"
    include_subtree: bool = True


class ArgumentFlattenRequest(BaseModel):
    node_id: str = "root"
    template: str = "markdown"
    include_references: bool = True
    style: str = "IEEE"
    latex_template: str = "generic_article"


MAX_FLATTEN_TASKS = 10


def register_argument(
    app: FastAPI,
    *,
    load_config,
    build_cloud_client,
    runtime_dir: Path,
    data_root: Path,
    rag_store_getter,
) -> None:
    """Register argument mapping routes. Works in simple-fallback mode always,
    and upgrades to advanced mode when the argument module is available."""

    from src.features import argument as _ARGUMENT_AVAILABLE

    if _ARGUMENT_AVAILABLE:
        from src.argument.models import (
            CreateTreeRequest, UpsertNodeRequest, ExpandRequest,
            ObserveRequest, BindRequest, ReviewRequest, FlattenRequest,
            NodeStatus, _now_iso,
        )
        from src.argument.store import ArgumentStore
        from src.argument.logic_checker import LogicChecker
        from src.argument.expander import ArgumentExpander
        from src.argument.observer import ArgumentObserver
        from src.argument.feedback_generator import FeedbackGenerator
        from src.argument.flatten import ArgumentFlattener

    # Advanced argument routes (always available — argument module is bundled)
    if _ARGUMENT_AVAILABLE:
        _astore = ArgumentStore(persist_dir=str(data_root))
        _logic_checker = LogicChecker()
        _argument_expander = ArgumentExpander(_astore)
        _argument_observer = ArgumentObserver(_astore)
        _feedback_generator = FeedbackGenerator()
        _argument_flattener = ArgumentFlattener()
        _flatten_tasks: dict[str, dict] = {}
        _flatten_output_dir = data_root / "argument_output"
        _flatten_output_dir.mkdir(parents=True, exist_ok=True)

        def _cleanup_flatten_tasks() -> None:
            done_ids = [tid for tid, t in _flatten_tasks.items() if t["status"] in ("done", "error")]
            if len(done_ids) <= MAX_FLATTEN_TASKS:
                return
            for tid in done_ids[:len(done_ids) - MAX_FLATTEN_TASKS]:
                del _flatten_tasks[tid]

        def _get_cloud_client_for_argument():
            config = load_config()
            trans_cfg = config.get("translator", {})
            cloud_cfg = trans_cfg.get("cloud", {})
            if not cloud_cfg.get("api_key"):
                return None
            return build_cloud_client(trans_cfg, cloud_cfg)

        def _ensure_rag_store() -> Any:
            return rag_store_getter()

        class _ArgumentError(HTTPException):
            def __init__(self, status_code: int, detail: str, error_code: str):
                self.error_code = error_code
                self.error_timestamp = _now_iso()
                super().__init__(status_code=status_code, detail=detail)

        @app.exception_handler(_ArgumentError)
        async def _argument_error_handler(request: Request, exc: _ArgumentError) -> JSONResponse:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail, "error_code": exc.error_code, "timestamp": exc.error_timestamp},
            )

        def _arg_error(status_code: int, detail: str, error_code: str):
            raise _ArgumentError(status_code, detail, error_code)

        @app.get("/api/argument/tree")
        def argument_get_tree_advanced():
            tree = _astore.get_tree()
            if tree.root_id is None:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")
            return tree.model_dump()

        @app.post("/api/argument/tree")
        def argument_create_tree_advanced(req: ArgumentTreeCreateRequest):
            _astore.create_tree(
                topic=req.topic,
                domain_tags=req.domain_tags,
                position=req.position,
            )
            return _astore.get_tree().model_dump()

        @app.put("/api/argument/node")
        def argument_upsert_node_advanced(req: ArgumentNodeRequest):
            if req.id and req.parent_id:
                parent = _astore.get_node(req.parent_id)
                if not parent:
                    _arg_error(400, "Invalid parent_id", "INVALID_PARENT")

            is_update = req.id is not None and req.id in _astore.get_tree().nodes
            node = _astore.upsert_node(
                **{k: v for k, v in req.model_dump().items() if v is not None},
            )
            return JSONResponse(content=node.model_dump(), status_code=200 if is_update else 201)

        @app.delete("/api/argument/node/{node_id}")
        def argument_delete_node_advanced(node_id: str, cascade: bool = False):
            deleted = _astore.delete_node(node_id, cascade=cascade)
            if not deleted:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return {"deleted": deleted, "message": f"Deleted {len(deleted)} nodes"}

        @app.get("/api/argument/node/{node_id}")
        def argument_get_node_advanced(node_id: str):
            node = _astore.get_node(node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return node.model_dump()

        @app.post("/api/argument/expand")
        async def argument_expand_advanced(req: ArgumentExpandRequest):
            cloud_client = _get_cloud_client_for_argument()
            result = await _argument_expander.expand(
                node_id=req.node_id,
                max_children=req.max_children,
                direction=req.direction,
                cloud_client=cloud_client,
            )
            if "error" in result:
                _arg_error(404, result["error"], "NODE_NOT_FOUND")
            return result

        @app.post("/api/argument/observe")
        def argument_observe_advanced(req: ArgumentObserveRequest):
            return _argument_observer.observe(
                node_id=req.node_id,
                content_hint=req.content_hint,
                rag_store=_ensure_rag_store(),
            )

        @app.post("/api/argument/bind")
        def argument_bind_advanced(req: ArgumentBindRequest):
            node = _astore.get_node(req.node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")

            citation_key = req.doc_id
            rag = _ensure_rag_store()
            if rag is not None:
                for doc in rag.list_documents():
                    if doc.id == req.doc_id:
                        citation_key = doc.title or req.doc_id
                        break

            updated = _astore.bind_reference(
                node_id=req.node_id,
                doc_id=req.doc_id,
                citation_key=citation_key,
                binding_type=req.binding_type,
                relevance_score=req.relevance_score,
            )
            if not updated:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")

            ref = next((r for r in updated.references if r.doc_id == req.doc_id), None)
            return {
                "node_id": req.node_id,
                "reference": ref.model_dump() if ref else None,
            }

        @app.delete("/api/argument/unbind/{node_id}/{doc_id}")
        def argument_unbind_advanced(node_id: str, doc_id: str):
            ok = _astore.unbind_reference(node_id, doc_id)
            if not ok:
                _arg_error(404, "Node or reference not found", "NODE_NOT_FOUND")
            return {"node_id": node_id, "doc_id": doc_id, "message": "Reference unbound successfully"}

        @app.post("/api/argument/review")
        async def argument_review_advanced(req: ArgumentReviewRequest):
            tree = _astore.get_tree()
            if not tree.root_id:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")

            target_id = req.node_id if req.node_id != "root" else tree.root_id
            if target_id not in tree.nodes:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            subtree_ids = _astore.get_subtree_ids(target_id) if req.include_subtree else [target_id]

            issues = _logic_checker.check(tree, subtree_ids)

            cloud_client = _get_cloud_client_for_argument()
            node_feedbacks = await _feedback_generator.generate(
                tree, issues, cloud_client=cloud_client,
            )

            for nid, fb in node_feedbacks.items():
                _astore.update_node_fields(
                    nid,
                    logic_status=fb["logic_status"],
                    rule_issues=fb["rule_issues"],
                    agent_feedback=fb["agent_feedback"],
                )

            overall = "pass"
            for fb in node_feedbacks.values():
                if fb["logic_status"] == "error":
                    overall = "error"
                    break
                if fb["logic_status"] == "warning":
                    overall = "warning"

            return {
                "reviewed_node_id": target_id,
                "reviewed_subtree": subtree_ids,
                "overall_status": overall,
                "rule_results": [iss.model_dump() for iss in issues],
                "node_feedbacks": node_feedbacks,
                "reviewed_at": _now_iso(),
            }

        @app.post("/api/argument/flatten")
        def argument_flatten_advanced(req: ArgumentFlattenRequest):
            tree = _astore.get_tree()
            if not tree.root_id:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")

            task_id = f"flatten_{uuid.uuid4().hex[:8]}"
            _flatten_tasks[task_id] = {
                "status": "processing",
                "request": req.model_dump(),
                "tree_snapshot": tree.model_dump(),
            }
            return {"task_id": task_id, "status": "processing"}

        @app.get("/api/argument/flatten/{task_id}")
        async def argument_flatten_stream_advanced(task_id: str):
            if task_id not in _flatten_tasks:
                _arg_error(404, "Task not found", "TASK_NOT_FOUND")

            task = _flatten_tasks[task_id]
            tree_data = task["tree_snapshot"]
            req = FlattenRequest(**task["request"])
            cloud_client = _get_cloud_client_for_argument()

            async def _generate():
                try:
                    async for event in _argument_flattener.flatten_stream(
                        tree_data=tree_data,
                        template=req.template,
                        style=req.style,
                        include_references=req.include_references,
                        output_dir=str(_flatten_output_dir),
                        cloud_client=cloud_client,
                        rag_store=_ensure_rag_store(),
                        latex_template=req.latex_template,
                    ):
                        if event.get("event") == "complete":
                            import json as _json
                            data = _json.loads(event.get("data", "{}"))
                            task["output_path"] = data.get("output_path", "")
                        yield event
                    task["status"] = "done"
                except Exception:
                    task["status"] = "error"
                    raise
                finally:
                    _cleanup_flatten_tasks()

            return EventSourceResponse(_generate())

        @app.get("/api/argument/download/{task_id}")
        def argument_download_advanced(task_id: str):
            if task_id not in _flatten_tasks:
                _arg_error(404, "Task not found", "TASK_NOT_FOUND")
            task = _flatten_tasks[task_id]
            if task.get("status") != "done":
                _arg_error(400, "Task not completed yet", "TASK_NOT_FOUND")
            output_path = Path(task.get("output_path", ""))
            if not output_path.exists():
                _arg_error(404, "Output file not found", "TASK_NOT_FOUND")
            content_types = {
                ".md": "text/markdown",
                ".tex": "text/x-latex",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            ct = content_types.get(output_path.suffix, "application/octet-stream")
            return FileResponse(output_path, media_type=ct, filename=output_path.name)

        @app.get("/api/argument/recommendations/{node_id}")
        def argument_recommendations(node_id: str):
            node = _astore.get_node(node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return {
                "node_id": node_id,
                "references": [r.model_dump() for r in node.references],
            }
