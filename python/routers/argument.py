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

    # Try to import advanced argument subsystem
    try:
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
        _ARGUMENT_AVAILABLE = True
    except ImportError:
        _ARGUMENT_AVAILABLE = False

    output_dir = data_root / "output"

    # ── Simple fallback argument routes (always registered) ──

    argument_tasks: dict[str, dict] = {}

    def _argument_store():
        from src.argument import ArgumentStore
        return ArgumentStore(runtime_dir / "data")

    def _argument_tree_or_404() -> dict:
        tree = _argument_store().load()
        if not tree:
            raise HTTPException(404, "Argument tree not found")
        return tree

    def _argument_node_or_404(tree: dict, node_id: str) -> dict:
        real_id = tree.get("root_id") if node_id == "root" else node_id
        node = tree.get("nodes", {}).get(real_id)
        if not node:
            raise HTTPException(404, "Node not found")
        return node

    def _argument_child_topics(topic: str, max_children: int) -> list[dict]:
        topic_l = topic.lower()
        if any(key in topic_l for key in ("control", "stability", "compensator", "校正", "控制", "稳定")):
            topics = [
                ("System modeling", ["control_theory", "modeling"]),
                ("Stability analysis", ["control_theory", "stability"]),
                ("Simulation validation", ["simulation", "validation"]),
                ("Comparative experiment", ["experiment", "baseline"]),
            ]
        else:
            topics = [
                ("Problem framing", ["background"]),
                ("Method design", ["method"]),
                ("Evidence and references", ["evidence"]),
                ("Evaluation and conclusion", ["evaluation"]),
            ]
        return [{"topic": t, "domain_tags": tags} for t, tags in topics[: max(1, min(max_children, 8))]]

    def _argument_markdown(tree: dict, node_id: str, include_references: bool) -> str:
        nodes = tree.get("nodes", {})
        start_id = tree.get("root_id") if node_id == "root" else node_id
        lines: list[str] = []

        def walk(nid: str) -> None:
            node = nodes[nid]
            level = min(int(node.get("depth", 0)) + 1, 6)
            lines.append(f"{'#' * level} {node.get('topic', 'Untitled')}")
            if node.get("content"):
                lines.extend(["", node["content"]])
            if include_references and node.get("references"):
                refs = ", ".join(r.get("citation_key") or r.get("doc_id", "") for r in node["references"])
                lines.extend(["", f"References: {refs}"])
            lines.append("")
            for child_id in node.get("children", []):
                if child_id in nodes:
                    walk(child_id)

        walk(start_id)
        return "\n".join(lines).strip() + "\n"

    @app.post("/api/argument/tree", status_code=201)
    async def argument_create_tree_fallback(req: ArgumentTreeCreateRequest):
        if _ARGUMENT_AVAILABLE:
            return argument_create_tree_advanced(req)
        return _argument_store().create_tree(req.topic, req.domain_tags, req.position)

    @app.get("/api/argument/tree")
    async def argument_get_tree_fallback():
        if _ARGUMENT_AVAILABLE:
            return argument_get_tree_advanced()
        return _argument_tree_or_404()

    @app.put("/api/argument/node")
    async def argument_upsert_node_fallback(req: ArgumentNodeRequest):
        if _ARGUMENT_AVAILABLE:
            return argument_upsert_node_advanced(req)
        store = _argument_store()
        tree = store.load()
        if not tree:
            tree = store.create_tree(req.topic, req.domain_tags, req.position)
            return tree["nodes"][tree["root_id"]]
        try:
            node, _created = store.upsert_node(
                tree,
                topic=req.topic,
                parent_id=req.parent_id,
                content=req.content,
                domain_tags=req.domain_tags,
                position=req.position,
                node_id=req.id,
            )
            return node
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/argument/node/{node_id}")
    async def argument_get_node_fallback(node_id: str):
        if _ARGUMENT_AVAILABLE:
            return argument_get_node_advanced(node_id)
        tree = _argument_tree_or_404()
        return _argument_node_or_404(tree, node_id)

    @app.delete("/api/argument/node/{node_id}")
    async def argument_delete_node_fallback(node_id: str, cascade: bool = False):
        if _ARGUMENT_AVAILABLE:
            return argument_delete_node_advanced(node_id, cascade)
        store = _argument_store()
        tree = _argument_tree_or_404()
        try:
            deleted = store.delete_node(tree, node_id, cascade)
            return {"deleted": deleted, "message": f"Deleted {len(deleted)} nodes"}
        except KeyError:
            raise HTTPException(404, "Node not found")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/argument/expand")
    async def argument_expand_fallback(req: ArgumentExpandRequest):
        if _ARGUMENT_AVAILABLE:
            return await argument_expand_advanced(req)
        store = _argument_store()
        tree = _argument_tree_or_404()
        parent = _argument_node_or_404(tree, req.node_id)
        children = []
        base_x = float(parent.get("position", {}).get("x", 400))
        base_y = float(parent.get("position", {}).get("y", 100)) + 140
        for index, child in enumerate(_argument_child_topics(parent.get("topic", ""), req.max_children)):
            node, _ = store.upsert_node(
                tree,
                topic=child["topic"],
                parent_id=parent["id"],
                domain_tags=child["domain_tags"],
                position={"x": base_x + index * 160 - (req.max_children - 1) * 80, "y": base_y},
            )
            children.append(node)
        return {"parent_id": parent["id"], "children": children}

    @app.post("/api/argument/observe")
    async def argument_observe_fallback(req: ArgumentObserveRequest):
        if _ARGUMENT_AVAILABLE:
            return argument_observe_advanced(req)
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, req.node_id)
        return {"node_id": node["id"], "observations": []}

    @app.post("/api/argument/bind")
    async def argument_bind_fallback(req: ArgumentBindRequest):
        if _ARGUMENT_AVAILABLE:
            return argument_bind_advanced(req)
        store = _argument_store()
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, req.node_id)
        store.bind_reference(
            tree, node["id"], req.doc_id,
            citation_key=req.doc_id,
            binding_type=req.binding_type,
            relevance_score=req.relevance_score,
        )
        return {"node_id": node["id"], "doc_id": req.doc_id, "message": "Reference bound successfully"}

    @app.delete("/api/argument/bind/{node_id}/{doc_id}")
    async def argument_unbind_fallback(node_id: str, doc_id: str):
        if _ARGUMENT_AVAILABLE:
            return argument_unbind_advanced(node_id, doc_id)
        store = _argument_store()
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, node_id)
        store.unbind_reference(tree, node["id"], doc_id)
        return {"node_id": node["id"], "doc_id": doc_id, "message": "Reference unbound successfully"}

    @app.post("/api/argument/review")
    async def argument_review_fallback(req: ArgumentReviewRequest):
        if _ARGUMENT_AVAILABLE:
            return await argument_review_advanced(req)
        from src.argument import check_argument_tree
        store = _argument_store()
        tree = _argument_tree_or_404()
        result = check_argument_tree(tree, req.node_id, req.include_subtree)
        feedbacks = {}
        for nid in result["reviewed_subtree"]:
            issues = [i for i in result["rule_results"] if nid in i.get("node_ids", [])]
            node = tree["nodes"][nid]
            node["logic_status"] = "warning" if issues else "pass"
            node["rule_issues"] = [i["issue_code"] for i in issues]
            node["agent_feedback"] = issues[0]["suggestion"] if issues else None
            feedbacks[nid] = {
                "logic_status": node["logic_status"],
                "rule_issues": node["rule_issues"],
                "agent_feedback": node["agent_feedback"],
            }
        store.save(tree)
        return {**result, "node_feedbacks": feedbacks, "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    @app.post("/api/argument/flatten")
    async def argument_flatten_fallback(req: ArgumentFlattenRequest):
        if _ARGUMENT_AVAILABLE:
            return argument_flatten_advanced(req)
        tree = _argument_tree_or_404()
        _argument_node_or_404(tree, req.node_id)
        task_id = f"flatten_task_{uuid.uuid4().hex[:8]}"
        out_dir = runtime_dir / "data" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{task_id}.md"
        content = _argument_markdown(tree, req.node_id, req.include_references)
        output_path.write_text(content, encoding="utf-8")
        argument_tasks[task_id] = {
            "task_id": task_id,
            "status": "complete",
            "output_path": str(output_path),
            "word_count": len(content.split()),
            "reference_count": content.count("References:"),
        }
        return {"task_id": task_id, "status": "processing"}

    @app.get("/api/argument/flatten/{task_id}/stream")
    async def argument_flatten_stream_fallback(task_id: str):
        if _ARGUMENT_AVAILABLE:
            return await argument_flatten_stream_advanced(task_id)
        task = argument_tasks.get(task_id)
        if not task:
            raise HTTPException(404, "Task not found")

        async def _stream():
            yield {"event": "complete", "data": json.dumps(task, ensure_ascii=False)}

        return EventSourceResponse(_stream(), media_type="text/event-stream")

    @app.get("/api/argument/download/{task_id}")
    async def argument_download_fallback(task_id: str):
        if _ARGUMENT_AVAILABLE:
            return argument_download_advanced(task_id)
        task = argument_tasks.get(task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return FileResponse(task["output_path"], media_type="text/markdown", filename=f"{task_id}.md")

    # ── Advanced argument routes (only when module available) ──

    if _ARGUMENT_AVAILABLE:
        _astore = ArgumentStore(persist_dir=str(data_root))
        _logic_checker = LogicChecker()
        _argument_expander = ArgumentExpander(_astore)
        _argument_observer = ArgumentObserver(_astore)
        _feedback_generator = FeedbackGenerator()
        _argument_flattener = ArgumentFlattener()
        _flatten_tasks: dict[str, dict] = {}

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

        def argument_get_tree_advanced():
            tree = _astore.get_tree()
            if tree.root_id is None:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")
            return tree.model_dump()

        def argument_create_tree_advanced(req: ArgumentTreeCreateRequest):
            _astore.create_tree(
                topic=req.topic,
                domain_tags=req.domain_tags,
                position=req.position,
            )
            return _astore.get_tree().model_dump()

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

        def argument_delete_node_advanced(node_id: str, cascade: bool):
            deleted = _astore.delete_node(node_id, cascade=cascade)
            if not deleted:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return {"deleted": deleted, "message": f"Deleted {len(deleted)} nodes"}

        def argument_get_node_advanced(node_id: str):
            node = _astore.get_node(node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return node.model_dump()

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

        def argument_observe_advanced(req: ArgumentObserveRequest):
            return _argument_observer.observe(
                node_id=req.node_id,
                content_hint=req.content_hint,
                rag_store=_ensure_rag_store(),
            )

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
                binding_type=req.binding_type.value,
                relevance_score=req.relevance_score,
            )
            if not updated:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")

            ref = next((r for r in updated.references if r.doc_id == req.doc_id), None)
            return {
                "node_id": req.node_id,
                "reference": ref.model_dump() if ref else None,
            }

        def argument_unbind_advanced(node_id: str, doc_id: str):
            ok = _astore.unbind_reference(node_id, doc_id)
            if not ok:
                _arg_error(404, "Node or reference not found", "NODE_NOT_FOUND")
            return {"node_id": node_id, "doc_id": doc_id, "message": "Reference unbound successfully"}

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
                        output_dir=output_dir,
                        cloud_client=cloud_client,
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
