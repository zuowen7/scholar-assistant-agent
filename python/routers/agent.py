"""Agent chat and RAG document management routes."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# Lazy imports — these may fail if chromadb is not installed
try:
    from src.agent.agent import AgentLoop
    from src.agent.context_compressor import ContextCompressor
    from src.agent.memory import MemoryManager
    from src.agent.models import Message, SessionState
    from src.agent.prompt_builder import PromptBuilder
    from src.agent.rag import RAGStore
    from src.agent.session import AgentSession, SessionConfig
    from src.agent.session_store import SessionStore
    from src.agent.skill_system import SkillRegistry
    from src.agent.tools import create_default_registry
    from src.agent.trajectory import TrajectoryRecorder
    from src.agent.workspace import WorkspaceEnv
    from src.agent.change_journal import ChangeJournal
    from src.translator.cloud_client import PROVIDER_PRESETS
    _AGENT_AVAILABLE = True
except ImportError:
    _AGENT_AVAILABLE = False

_V2_TOOL_WHITELIST = frozenset({
    "read_file", "list_directory", "search_files",
    "rag_retrieve", "web_search", "arxiv_search",
    "run_command", "git_op",
})


class ChatRequest(BaseModel):
    message: str = Field(max_length=100_000)
    history: list[dict] | None = Field(default=None, max_length=50)
    context_text: str | None = Field(default=None, max_length=500_000)
    constraints: str | None = Field(default=None, max_length=10_000)
    workspace_root: str | None = None


class RAGIngestRequest(BaseModel):
    doc_id: str = Field(max_length=256)
    text: str = Field(max_length=5_000_000)
    title: str = Field(default="", max_length=500)


class V2ToolRequest(BaseModel):
    tool: str = Field(max_length=128)
    args: dict = Field(default={}, max_length=20)


class ApproveRequest(BaseModel):
    decision: str  # "allow_once" | "allow_session" | "deny"
    reason: str | None = None


def register_agent(
    app: FastAPI,
    *,
    cloud_only: bool,
    load_config,
    runtime_dir: Path,
    data_root: Path,
) -> dict:
    """Register Agent chat + RAG routes. Returns state dict with rag_store getter."""
    _shared: dict = {}
    _init_lock = asyncio.Lock()
    _session_pool: dict[str, AgentSession] = {}
    _session_store: SessionStore | None = None

    def get_rag_store():
        return _shared.get("rag_store")

    # ------------------------------------------------------------------
    # Shared resource initialization (RAG, Memory, Skills, etc.)
    # ------------------------------------------------------------------

    async def _ensure_shared() -> dict:
        """Initialize shared resources on first call, then cache."""
        if _shared:
            return _shared

        async with _init_lock:
            if _shared:
                return _shared

            config = load_config()
            agent_cfg = config.get("agent", {})
            trans_cfg = config.get("translator", {})
            workspace_root = agent_cfg.get("workspace_root", "")

            # RAG Store
            rag_cfg = agent_cfg.get("rag", {})
            rag_dir = runtime_dir / rag_cfg.get("persist_dir", "data/chromadb")
            rag_store = None
            try:
                rag_store = RAGStore(
                    persist_dir=str(rag_dir),
                    collection_name=rag_cfg.get("collection_name", "scholar_docs"),
                    chunk_size=rag_cfg.get("chunk_size", 512),
                    chunk_overlap=rag_cfg.get("chunk_overlap", 64),
                )
            except ModuleNotFoundError as e:
                if e.name != "chromadb":
                    raise
                logger.warning("chromadb not installed; Agent chat will run without RAG memory")

            # Persistent memory, skills, trajectory
            agent_data_dir = str(data_root / "agent")
            memory_manager = MemoryManager(data_dir=agent_data_dir)
            skill_registry = SkillRegistry(skills_dir=agent_data_dir + "/skills")
            trajectory_recorder = TrajectoryRecorder(data_dir=agent_data_dir + "/trajectories")

            # Tool registry (stateless tool functions, safe to share)
            use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            cloud_cfg = trans_cfg.get("cloud", {}) if use_cloud else {}
            tool_registry = create_default_registry(
                rag_store=rag_store,
                ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                model=agent_cfg.get("model", "qwen3:8b"),
                cloud_base_url=cloud_cfg.get("base_url", "https://api.openai.com/v1") if use_cloud else "",
                cloud_api_key=(cloud_cfg.get("api_key") or "").strip() if use_cloud else "",
                cloud_model=cloud_cfg.get("model", "gpt-4o") if use_cloud else "",
                workspace_root=workspace_root,
            )

            _shared.update({
                "rag_store": rag_store,
                "memory_manager": memory_manager,
                "skill_registry": skill_registry,
                "trajectory_recorder": trajectory_recorder,
                "tool_registry": tool_registry,
                "workspace_root": workspace_root,
            })

            # Session store (SQLite, Phase 4)
            nonlocal _session_store
            _session_store = SessionStore(db_path=str(data_root / "agent" / "sessions.db"))

            logger.info("Agent shared resources initialized (rag=%s)", rag_dir)
            return _shared

    # ------------------------------------------------------------------
    # Per-request AgentLoop factory
    # ------------------------------------------------------------------

    async def _create_agent(workspace_root: str | None = None) -> AgentLoop:
        """Create a fresh AgentLoop for this request using shared resources.

        workspace_root: if provided (from ChatRequest), overrides the config default
        and ensures workspace file-editing tools are available for this session.
        """
        shared = await _ensure_shared()
        config = load_config()
        agent_cfg = config.get("agent", {})
        trans_cfg = config.get("translator", {})

        use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
        cloud_cfg = trans_cfg.get("cloud", {})
        ollama_url = trans_cfg.get("ollama_base_url", "http://localhost:11434")

        # Resolve effective workspace: prefer request value over config value
        effective_workspace = (workspace_root or "").strip() or shared.get("workspace_root", "")

        # If request specifies a different workspace, build a per-request tool registry
        # that includes AWA v2 file-editing tools scoped to that workspace.
        if effective_workspace and effective_workspace != shared.get("workspace_root", ""):
            cloud_cfg_for_tools = trans_cfg.get("cloud", {}) if use_cloud else {}
            tool_registry = create_default_registry(
                rag_store=shared["rag_store"],
                ollama_base_url=ollama_url,
                model=agent_cfg.get("model", "qwen3:8b"),
                cloud_base_url=cloud_cfg_for_tools.get("base_url", "https://api.openai.com/v1") if use_cloud else "",
                cloud_api_key=(cloud_cfg_for_tools.get("api_key") or "").strip() if use_cloud else "",
                cloud_model=cloud_cfg_for_tools.get("model", "gpt-4o") if use_cloud else "",
                workspace_root=effective_workspace,
            )
            logger.info("Agent 使用请求级工作区: %s", effective_workspace)
        else:
            tool_registry = shared["tool_registry"]

        # Per-request compressor (owns HTTP client, cleaned up by AgentLoop.close())
        agent_model = agent_cfg.get("model", "qwen3:8b")
        compressor = ContextCompressor(
            max_window_tokens=agent_cfg.get("max_window_tokens", 32_000),
            threshold_percent=agent_cfg.get("compress_threshold", 0.50),
            ollama_base_url=ollama_url,
            summary_model=agent_model if not use_cloud else None,
            cloud_base_url=cloud_cfg.get("base_url", "") if use_cloud else "",
            cloud_api_key=(cloud_cfg.get("api_key") or "").strip() if use_cloud else "",
            cloud_model=cloud_cfg.get("model", "") if use_cloud else "",
        )
        prompt_builder = PromptBuilder(tool_registry=tool_registry)

        if use_cloud:
            key = (cloud_cfg.get("api_key") or "").strip()
            if key:
                agent_model = cloud_cfg.get("model", "gpt-4o")
                logger.info("Agent 使用云端 API: model=%s, provider=%s",
                            agent_model, cloud_cfg.get("provider", "openai"))

        return AgentLoop(
            ollama_base_url=ollama_url,
            model=agent_model,
            tool_registry=tool_registry,
            max_steps=agent_cfg.get("max_steps", 10),
            system_prompt=agent_cfg.get("system_prompt", ""),
            temperature=agent_cfg.get("temperature", 0.3),
            num_predict=agent_cfg.get("num_predict", 4096),
            timeout=trans_cfg.get("timeout", 300.0),
            context_compressor=compressor,
            prompt_builder=prompt_builder,
            memory_manager=shared["memory_manager"],
            skill_registry=shared["skill_registry"],
            trajectory_recorder=shared["trajectory_recorder"],
            rag_store=shared["rag_store"],
            cloud_base_url=cloud_cfg.get("base_url", "https://api.openai.com/v1") if use_cloud else "",
            cloud_api_key=(cloud_cfg.get("api_key") or "").strip() if use_cloud else "",
            cloud_model=cloud_cfg.get("model", "gpt-4o") if use_cloud else "",
            api_format=PROVIDER_PRESETS.get(cloud_cfg.get("provider", "openai"), {}).get("api_format", "openai") if use_cloud else "openai",
            memory_dir=str(data_root / "agent" / "memory"),
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        """Default chat endpoint — now forwards to v2 session-driven SSE."""
        return await v2_chat(req)

    @app.post("/api/chat/v1")
    async def chat_v1(req: ChatRequest):
        """Legacy v1 endpoint (deprecated, uses AgentLoop.run() directly)."""
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装，请安装 chromadb")

        agent = await _create_agent(workspace_root=req.workspace_root)

        history: list[Message] | None = None
        if req.history:
            history = [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in req.history
            ]

        message = req.message
        if req.context_text or req.constraints:
            enhancements: list[str] = []
            if req.context_text:
                enhancements.append(f"[参考文本]\n{req.context_text}")
            if req.constraints:
                enhancements.append(f"[约束要求]\n{req.constraints}")
            enhanced = "\n\n".join(enhancements) + f"\n\n[用户问题]\n{req.message}"
            message = enhanced

        async def _stream() -> AsyncGenerator[dict, None]:
            try:
                async for event in agent.run(message, history):
                    payload: dict = {"type": event.type, "content": event.content}
                    if event.metadata:
                        payload["metadata"] = event.metadata
                    yield {
                        "event": event.type,
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
            finally:
                await agent.close()

        return EventSourceResponse(
            _stream(),
            media_type="text/event-stream",
        )

    # ------------------------------------------------------------------
    # v2: AgentSession-driven SSE endpoint
    # ------------------------------------------------------------------

    @app.post("/api/agent/v2/chat")
    async def v2_chat(req: ChatRequest):
        """v2 SSE endpoint — AgentSession 状态机驱动，支持多任务编排。"""
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装，请安装 chromadb")

        shared = await _ensure_shared()
        agent = await _create_agent(workspace_root=req.workspace_root)

        history: list[Message] | None = None
        if req.history:
            history = [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in req.history
            ]

        message = req.message
        if req.context_text or req.constraints:
            enhancements: list[str] = []
            if req.context_text:
                enhancements.append(f"[参考文本]\n{req.context_text}")
            if req.constraints:
                enhancements.append(f"[约束要求]\n{req.constraints}")
            message = "\n\n".join(enhancements) + f"\n\n[用户问题]\n{req.message}"

        # Build workspace/journal if workspace_root is set
        workspace = None
        journal = None
        effective_ws = (req.workspace_root or "").strip()
        if effective_ws:
            try:
                workspace = WorkspaceEnv(root=effective_ws)
                journal = ChangeJournal(backup_root=workspace.backup_root_path())
            except Exception as e:
                logger.warning("v2 workspace 初始化失败: %s", e)

        # Event callback: dual-write to trajectory
        trajectory = shared["trajectory_recorder"]
        trajectory.start(message)

        def _on_event(event):
            trajectory.record_event(event)

        trajectory.start_event_stream("pending", message)

        session = AgentSession(
            agent=agent,
            workspace=workspace,
            journal=journal,
            config=SessionConfig(auto_approve=True),
            session_store=_session_store,
            event_callback=_on_event,
        )
        _session_pool[session.id] = session

        # Update event stream filename with actual session id
        if trajectory._event_stream_path:
            new_path = trajectory.data_dir / f"events_{session.id}.jsonl"
            try:
                trajectory._event_stream_path.rename(new_path)
                trajectory._event_stream_path = new_path
            except Exception:
                pass

        async def _v2_stream() -> AsyncGenerator[dict, None]:
            try:
                async for event in session.drive(message, history):
                    payload: dict = {
                        "type": event.type,
                        "content": event.content,
                        "event_id": event.event_id,
                    }
                    if event.metadata:
                        payload["metadata"] = event.metadata
                    yield {
                        "event": event.type,
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
            finally:
                _session_pool.pop(session.id, None)
                trajectory.finish_event_stream(success=session.state == SessionState.DONE)
                await agent.close()

        return EventSourceResponse(
            _v2_stream(),
            media_type="text/event-stream",
        )

    @app.post("/api/agent/v2/approve/{session_id}/{event_id}")
    async def v2_approve(session_id: str, event_id: str, req: ApproveRequest, request: Request):
        """v2 审批回流端点。"""
        if request.client.host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "仅允许本地访问")
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装")
        session = _session_pool.get(session_id)
        if session is None:
            raise HTTPException(404, f"Session {session_id} 不存在")
        ok = await session.approve(event_id, req.decision)
        if not ok:
            raise HTTPException(400, f"Event {event_id} 无待处理的审批")
        return {"status": "ok"}

    @app.post("/api/agent/v2/abort/{session_id}")
    async def v2_abort(session_id: str, request: Request):
        """v2 会话中止端点。"""
        if request.client.host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "仅允许本地访问")
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装")
        session = _session_pool.get(session_id)
        if session is None:
            raise HTTPException(404, f"Session {session_id} 不存在")
        await session.abort()
        return {"status": "ok"}

    @app.get("/api/agent/v2/sessions")
    async def v2_list_sessions(request: Request):
        """列出所有 v2 sessions（内存 + 持久化）。"""
        if request.client.host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "仅允许本地访问")

        # In-memory sessions take priority
        result = {
            s.id: {
                "id": s.id,
                "state": s.state.value if hasattr(s.state, "value") else s.state,
                "global_step": s.global_step,
                "tasks_total": s.task_queue.total_count,
                "tasks_done": s.task_queue.done_count,
                "source": "memory",
            }
            for s in _session_pool.values()
        }

        # Merge persisted sessions (not already in memory)
        if _session_store:
            try:
                for stored in _session_store.list_sessions(exclude_done=True):
                    if stored["id"] not in result:
                        result[stored["id"]] = {
                            "id": stored["id"],
                            "state": stored["state"],
                            "global_step": stored["global_step"],
                            "tasks_total": stored["tasks_total"],
                            "tasks_done": stored["tasks_done"],
                            "workspace_root": stored.get("workspace_root", ""),
                            "query": stored.get("query", ""),
                            "created_at": stored.get("created_at", ""),
                            "updated_at": stored.get("updated_at", ""),
                            "source": "store",
                        }
            except Exception as e:
                logger.warning("Failed to list stored sessions: %s", e)

        return list(result.values())

    @app.post("/api/agent/v2/resume/{session_id}")
    async def v2_resume(session_id: str, request: Request):
        """Resume a paused/persisted session via SSE."""
        if request.client.host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "仅允许本地访问")
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装")

        # Check in-memory first (client disconnected but session still alive)
        session = _session_pool.get(session_id)
        if session is not None:
            if session.state in (SessionState.DONE, SessionState.ABORTED):
                raise HTTPException(400, f"Session {session_id} already completed")

            agent = await _create_agent(
                workspace_root=str(session.workspace.root) if session.workspace else None
            )
            _session_pool[session_id] = session

            async def _resume_stream() -> AsyncGenerator[dict, None]:
                try:
                    async for event in session.resume(agent):
                        payload: dict = {
                            "type": event.type,
                            "content": event.content,
                            "event_id": event.event_id,
                        }
                        if event.metadata:
                            payload["metadata"] = event.metadata
                        yield {
                            "event": event.type,
                            "data": json.dumps(payload, ensure_ascii=False),
                        }
                finally:
                    _session_pool.pop(session_id, None)
                    await agent.close()

            return EventSourceResponse(_resume_stream(), media_type="text/event-stream")

        # Try restoring from SessionStore
        if _session_store is None:
            raise HTTPException(404, f"Session {session_id} 不存在且无持久化存储")

        data = _session_store.load(session_id)
        if data is None:
            raise HTTPException(404, f"Session {session_id} 不存在")

        if data["state"] in ("DONE", "ABORTED"):
            raise HTTPException(400, f"Session {session_id} already completed")

        # Reconstruct session from stored data
        workspace = None
        journal = None
        ws_root = data.get("workspace_root", "")
        if ws_root:
            try:
                workspace = WorkspaceEnv(root=ws_root)
                journal = ChangeJournal(backup_root=workspace.backup_root_path())
            except Exception as e:
                logger.warning("Resume workspace 初始化失败: %s", e)

        config = SessionConfig(
            max_task_steps=data["config"].get("max_task_steps", 50),
            max_global_steps=data["config"].get("max_global_steps", 200),
            auto_approve=data["config"].get("auto_approve", True),
            approval_timeout=data["config"].get("approval_timeout", 600),
        )

        agent = await _create_agent(workspace_root=ws_root or None)
        messages = _session_store.deserialize_messages(data["messages"])
        task_queue = _session_store.deserialize_task_queue(data["task_queue"])

        session = AgentSession(
            agent=agent,
            workspace=workspace,
            journal=journal,
            config=config,
            session_id=session_id,
            session_store=_session_store,
            created_at=data.get("created_at", ""),
        )
        session.messages = messages
        session.task_queue = task_queue
        session.global_step = data["global_step"]
        session.state = SessionState.EXECUTING
        _session_pool[session_id] = session

        async def _restored_stream() -> AsyncGenerator[dict, None]:
            try:
                async for event in session.resume(agent):
                    payload: dict = {
                        "type": event.type,
                        "content": event.content,
                        "event_id": event.event_id,
                    }
                    if event.metadata:
                        payload["metadata"] = event.metadata
                    yield {
                        "event": event.type,
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
            finally:
                _session_pool.pop(session_id, None)
                await agent.close()

        return EventSourceResponse(_restored_stream(), media_type="text/event-stream")

    @app.post("/api/agent/v2/undo/{session_id}")
    async def v2_undo(session_id: str, request: Request):
        """v2 Undo 端点 — 回退最近 N 次破坏性操作。"""
        if request.client.host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "仅允许本地访问")
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装")
        session = _session_pool.get(session_id)
        if session is None:
            raise HTTPException(404, f"Session {session_id} 不存在")
        if session.journal is None:
            raise HTTPException(400, "Session 无变更日志")
        reverted = session.journal.undo(count=1)
        return {"status": "ok", "reverted": len(reverted)}

    @app.get("/api/rag/documents")
    async def list_rag_documents():
        rag_store = _shared.get("rag_store") if _shared else None
        if rag_store is None:
            return []
        docs = rag_store.list_documents()
        return [
            {"id": d.id, "title": d.title, "chunk_count": d.chunk_count, "metadata": d.metadata}
            for d in docs
        ]

    @app.delete("/api/rag/documents/{doc_id}")
    async def delete_rag_document(doc_id: str):
        rag_store = _shared.get("rag_store") if _shared else None
        if rag_store is None:
            raise HTTPException(503, "RAG 未初始化")
        rag_store.delete_document(doc_id)
        return {"status": "deleted", "doc_id": doc_id}

    @app.post("/api/rag/ingest")
    async def rag_ingest(req: RAGIngestRequest):
        rag_store = _shared.get("rag_store") if _shared else None
        if rag_store is None:
            raise HTTPException(503, "RAG 未初始化")
        rag_store.ingest_document(
            doc_id=req.doc_id,
            text=req.text,
            title=req.title,
        )
        return {"status": "ok", "doc_id": req.doc_id}

    @app.post("/api/rag/upload")
    async def rag_upload(file: UploadFile = File(...)):
        rag_store = _shared.get("rag_store") if _shared else None
        if rag_store is None:
            raise HTTPException(503, "RAG 未初始化")
        text_bytes = await file.read()
        text = text_bytes.decode("utf-8", errors="replace")
        doc_id = file.filename or "uploaded"
        rag_store.ingest_document(
            doc_id=doc_id,
            text=text,
            title=file.filename or "Uploaded document",
        )
        return {"status": "ok", "doc_id": doc_id, "chars": len(text)}

    @app.get("/api/agent/stats")
    async def agent_stats():
        if not _AGENT_AVAILABLE or not _shared:
            return {"available": False}
        config = load_config()
        agent_cfg = config.get("agent", {})
        return {
            "available": True,
            "model": agent_cfg.get("model", "qwen3:8b"),
            "max_steps": agent_cfg.get("max_steps", 10),
        }

    # --- AWA v2: Direct tool invocation endpoint (for testing / Phase 1 validation) ---

    @app.post("/api/agent/v2/tool")
    async def v2_tool_invoke(req: V2ToolRequest, request: Request):
        """直接调用 AWA v2 工作区工具（开发调试用）。"""
        if request.client.host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "仅允许本地访问")
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装")
        if req.tool not in _V2_TOOL_WHITELIST:
            raise HTTPException(403, f"工具 '{req.tool}' 不在白名单中，允许: {sorted(_V2_TOOL_WHITELIST)}")

        shared = await _ensure_shared()
        tool_def = shared["tool_registry"].get(req.tool)
        if tool_def is None:
            raise HTTPException(404, f"工具 '{req.tool}' 不存在")

        try:
            if asyncio.iscoroutinefunction(tool_def.fn):
                result = await asyncio.to_thread(tool_def.fn, **req.args)
            else:
                result = tool_def.fn(**req.args)
            # result 是 JSON 字符串
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return {"result": result}
        except TypeError as e:
            raise HTTPException(400, f"参数错误: {e}")
        except Exception as e:
            raise HTTPException(500, f"工具执行失败: {e}")

    async def shutdown():
        mm = _shared.get("memory_manager")
        if mm:
            mm.close()
        if _session_store:
            _session_store.close()
        _shared.clear()

    return {
        "get_rag_store": get_rag_store,
        "shutdown": shutdown,
    }
