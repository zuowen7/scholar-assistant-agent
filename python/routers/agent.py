"""Agent chat and RAG document management routes."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# Lazy imports — these may fail if chromadb is not installed
try:
    from src.agent.agent import AgentLoop
    from src.agent.context_compressor import ContextCompressor
    from src.agent.memory import MemoryManager
    from src.agent.models import Message
    from src.agent.prompt_builder import PromptBuilder
    from src.agent.rag import RAGStore
    from src.agent.skill_system import SkillRegistry
    from src.agent.tools import create_default_registry
    from src.agent.trajectory import TrajectoryRecorder
    from src.agent.vram_manager import MultiplexingScheduler
    from src.translator.cloud_client import PROVIDER_PRESETS
    _AGENT_AVAILABLE = True
except ImportError:
    _AGENT_AVAILABLE = False


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None
    context_text: str | None = None
    constraints: str | None = None
    workspace_root: str | None = None


class RAGIngestRequest(BaseModel):
    doc_id: str
    text: str
    title: str = ""


class V2ToolRequest(BaseModel):
    tool: str
    args: dict = {}


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
    _agent_instance: AgentLoop | None = None
    _rag_store: RAGStore | None = None
    _agent_lock = asyncio.Lock()

    def get_rag_store():
        return _rag_store

    async def _get_agent() -> AgentLoop:
        nonlocal _agent_instance, _rag_store

        if _agent_instance is not None:
            return _agent_instance

        async with _agent_lock:
            if _agent_instance is not None:
                return _agent_instance

            config = load_config()
            agent_cfg = config.get("agent", {})
            trans_cfg = config.get("translator", {})
            workspace_root = agent_cfg.get("workspace_root", "")

            rag_cfg = agent_cfg.get("rag", {})
            rag_dir = runtime_dir / rag_cfg.get("persist_dir", "data/chromadb")
            try:
                _rag_store = RAGStore(
                    persist_dir=str(rag_dir),
                    collection_name=rag_cfg.get("collection_name", "scholar_docs"),
                    chunk_size=rag_cfg.get("chunk_size", 512),
                    chunk_overlap=rag_cfg.get("chunk_overlap", 64),
                )
            except ModuleNotFoundError as e:
                if e.name != "chromadb":
                    raise
                logger.warning("chromadb not installed; Agent chat will run without RAG memory")
                _rag_store = None

            use_cloud_tools = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            cloud_cfg_tools = trans_cfg.get("cloud", {}) if use_cloud_tools else {}
            registry = create_default_registry(
                rag_store=_rag_store,
                ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                model=agent_cfg.get("model", "qwen3:8b"),
                cloud_base_url=cloud_cfg_tools.get("base_url", "https://api.openai.com/v1") if use_cloud_tools else "",
                cloud_api_key=(cloud_cfg_tools.get("api_key") or "").strip() if use_cloud_tools else "",
                cloud_model=cloud_cfg_tools.get("model", "gpt-4o") if use_cloud_tools else "",
                workspace_root=workspace_root,
            )

            scheduler = None
            vram_cfg = agent_cfg.get("vram", {})
            _use_cloud_engine = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            if vram_cfg.get("enabled", True) and not _use_cloud_engine:
                scheduler = MultiplexingScheduler(
                    ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                    model=agent_cfg.get("model", "qwen3:8b"),
                )

            agent_data_dir = str(data_root / "agent")
            memory_manager = MemoryManager(data_dir=agent_data_dir)
            skill_registry = SkillRegistry(skills_dir=agent_data_dir + "/skills")
            trajectory_recorder = TrajectoryRecorder(data_dir=agent_data_dir + "/trajectories")

            ollama_url = trans_cfg.get("ollama_base_url", "http://localhost:11434")
            agent_model = agent_cfg.get("model", "qwen3:8b")
            # use_cloud_tools 已在上方定义：cloud_only or engine == "cloud"
            _compress_cloud_cfg = cloud_cfg_tools if use_cloud_tools else {}
            compressor = ContextCompressor(
                max_window_tokens=agent_cfg.get("max_window_tokens", 32_000),
                threshold_percent=agent_cfg.get("compress_threshold", 0.50),
                ollama_base_url=ollama_url,
                summary_model=agent_model if not use_cloud_tools else None,
                cloud_base_url=_compress_cloud_cfg.get("base_url", "") if use_cloud_tools else "",
                cloud_api_key=(_compress_cloud_cfg.get("api_key") or "").strip() if use_cloud_tools else "",
                cloud_model=_compress_cloud_cfg.get("model", "") if use_cloud_tools else "",
            )
            prompt_builder = PromptBuilder(tool_registry=registry)

            use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            cloud_cfg = trans_cfg.get("cloud", {})
            if use_cloud:
                key = (cloud_cfg.get("api_key") or "").strip()
                if key:
                    agent_model = cloud_cfg.get("model", "gpt-4o")
                    logger.info("Agent 使用云端 API: model=%s, provider=%s",
                                agent_model, cloud_cfg.get("provider", "openai"))

            _agent_instance = AgentLoop(
                ollama_base_url=ollama_url,
                model=agent_model,
                tool_registry=registry,
                scheduler=scheduler,
                max_steps=agent_cfg.get("max_steps", 10),
                system_prompt=agent_cfg.get("system_prompt", ""),
                temperature=agent_cfg.get("temperature", 0.3),
                num_predict=agent_cfg.get("num_predict", 4096),
                timeout=trans_cfg.get("timeout", 300.0),
                context_compressor=compressor,
                prompt_builder=prompt_builder,
                memory_manager=memory_manager,
                skill_registry=skill_registry,
                trajectory_recorder=trajectory_recorder,
                rag_store=_rag_store,
                cloud_base_url=cloud_cfg.get("base_url", "https://api.openai.com/v1") if use_cloud else "",
                cloud_api_key=(cloud_cfg.get("api_key") or "").strip() if use_cloud else "",
                cloud_model=cloud_cfg.get("model", "gpt-4o") if use_cloud else "",
                api_format=PROVIDER_PRESETS.get(cloud_cfg.get("provider", "openai"), {}).get("api_format", "openai") if use_cloud else "openai",
                memory_dir=agent_data_dir + "/memory",
            )

            logger.info("Agent 初始化完成 (model=%s, rag=%s)",
                        agent_cfg.get("model"), rag_dir)
            return _agent_instance

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装，请安装 chromadb")

        agent = await _get_agent()

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
            async for event in agent.run(message, history):
                payload: dict = {"type": event.type, "content": event.content}
                if event.metadata:
                    payload["metadata"] = event.metadata
                yield {
                    "event": event.type,
                    "data": json.dumps(payload, ensure_ascii=False),
                }

        return EventSourceResponse(
            _stream(),
            media_type="text/event-stream",
        )

    @app.get("/api/rag/documents")
    async def list_rag_documents():
        if _rag_store is None:
            return []
        docs = _rag_store.list_documents()
        return [
            {"id": d.id, "title": d.title, "chunk_count": d.chunk_count, "metadata": d.metadata}
            for d in docs
        ]

    @app.delete("/api/rag/documents/{doc_id}")
    async def delete_rag_document(doc_id: str):
        if _rag_store is None:
            raise HTTPException(503, "RAG 未初始化")
        _rag_store.delete_document(doc_id)
        return {"status": "deleted", "doc_id": doc_id}

    @app.post("/api/rag/ingest")
    async def rag_ingest(req: RAGIngestRequest):
        if _rag_store is None:
            raise HTTPException(503, "RAG 未初始化")
        _rag_store.ingest_document(
            doc_id=req.doc_id,
            text=req.text,
            title=req.title,
        )
        return {"status": "ok", "doc_id": req.doc_id}

    @app.post("/api/rag/upload")
    async def rag_upload(file: UploadFile = File(...)):
        if _rag_store is None:
            raise HTTPException(503, "RAG 未初始化")
        text_bytes = await file.read()
        text = text_bytes.decode("utf-8", errors="replace")
        doc_id = file.filename or "uploaded"
        _rag_store.ingest_document(
            doc_id=doc_id,
            text=text,
            title=file.filename or "Uploaded document",
        )
        return {"status": "ok", "doc_id": doc_id, "chars": len(text)}

    @app.get("/api/agent/stats")
    async def agent_stats():
        if not _AGENT_AVAILABLE or _agent_instance is None:
            return {"available": False}
        return {
            "available": True,
            "model": _agent_instance.model,
            "max_steps": _agent_instance.max_steps,
        }

    # --- AWA v2: Direct tool invocation endpoint (for testing / Phase 1 validation) ---

    @app.post("/api/agent/v2/tool")
    async def v2_tool_invoke(req: V2ToolRequest):
        """直接调用 AWA v2 工作区工具（开发调试用）。"""
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装")

        agent = await _get_agent()
        tool_def = agent.tool_registry.get(req.tool)
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
        nonlocal _agent_instance
        if _agent_instance is not None:
            await _agent_instance.close()
            _agent_instance.memory.close()

    return {
        "get_rag_store": get_rag_store,
        "shutdown": shutdown,
    }
