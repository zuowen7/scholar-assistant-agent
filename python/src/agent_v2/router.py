"""Agent V2 router — 新 Runtime 接入 FastAPI。

前端 useAgentChat.ts 调用的端点:
  POST /api/agent/v2/chat            — 主对话 (SSE)
  POST /api/agent/v2/resume/{sid}    — 恢复会话 (SSE)
  POST /api/agent/v2/approve/{sid}/{eid} — 审批工具调用
  POST /api/agent/v2/abort/{sid}     — 中止会话
  GET  /api/agent/v2/sessions        — 会话列表
  GET  /api/agent/v2/tools            — 工具列表
  GET  /api/agent/v2/workflows/{id}/messages — 工作流消息 (stub)
  POST /api/agent/v2/workflows/cleanup        — 清理工作流 (stub)
  DELETE /api/agent/v2/workflows/{id}          — 删除工作流 (stub)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.sse_adapter import agent_event_to_sse_stream
from src.agent_v2.tools.registry import create_default_registry
from src.agent_v2.tools.academic_tools import register_academic_tools
from src.agent_v2.types import AgentEvent

logger = logging.getLogger(__name__)

# Session 保存在 python/ 目录下，避开 Tauri src-tauri/ 文件监视器
_DEFAULT_SESSION_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "agent_v2" / "sessions"
_SESSION_DIR = Path(os.environ.get("AGENT_SESSION_DIR", str(_DEFAULT_SESSION_DIR)))
_SESSION_POOL: dict[str, ConversationRuntime] = {}
_SESSION_LOCK = asyncio.Lock()
_SESSION_TTL = 3600


class ChatRequestV2(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    history: list[dict] | None = Field(default=None, max_length=50)
    context_text: str | None = Field(default=None, max_length=500_000)
    context_file: str | None = Field(default=None, max_length=4_000)
    constraints: str | None = Field(default=None, max_length=10_000)
    workspace_root: str | None = None
    workflow_id: str | None = None


class ApproveRequest(BaseModel):
    decision: str = "allow_once"  # allow_once, allow_session, deny
    reason: str | None = None


# ---------------------------------------------------------------------------
# Provider / Runtime factory
# ---------------------------------------------------------------------------

def _load_cloud_config() -> dict:
    """从 config 文件读取翻译器云配置（合并 default.yaml + local.yaml）。"""
    import yaml
    # __file__ = .../python/src/agent_v2/router.py → 3x parent = python/
    _python_root = Path(__file__).resolve().parent.parent.parent
    merged = {}

    # 1. 先读 default.yaml
    default_path = _python_root / "config" / "default.yaml"
    if default_path.is_file():
        try:
            with open(default_path, encoding="utf-8") as f:
                merged = yaml.safe_load(f) or {}
        except Exception:
            pass

    # 2. 用 local.yaml 覆盖
    local_path = _python_root / "config" / "default.local.yaml"
    if local_path.is_file():
        try:
            with open(local_path, encoding="utf-8") as f:
                local = yaml.safe_load(f) or {}
            _deep_merge(merged, local)
        except Exception:
            pass

    return merged.get("translator", {}).get("cloud", {})


def _deep_merge(base: dict, override: dict) -> None:
    """递归合并 override 到 base。"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _create_provider():
    from src.agent_v2.providers.openai_compat import OpenAiCompatProvider
    model = os.environ.get("AGENT_MODEL", "").strip()

    # 1. 环境变量优先：ANTHROPIC_API_KEY
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
        logger.info("Agent V2: using Anthropic — %s", model or "claude-sonnet-4-6")
        return OpenAiCompatProvider(base_url=base, api_key=anthropic_key, model=model or "claude-sonnet-4-6")

    # 2. 环境变量：OPENAI_API_KEY 或自定义 OPENAI_BASE_URL
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    if openai_key or openai_base != "https://api.openai.com/v1":
        logger.info("Agent V2: using OpenAI-compatible — %s @ %s", model or "gpt-4o", openai_base)
        return OpenAiCompatProvider(base_url=openai_base, api_key=openai_key, model=model or "gpt-4o")

    # 3. 读取 config/default.local.yaml 中的翻译器云配置（DeepSeek 等）
    cloud = _load_cloud_config()
    if cloud:
        api_key = cloud.get("api_key", "").strip()
        base_url = cloud.get("base_url", "https://api.deepseek.com/v1").strip()
        cloud_model = cloud.get("model", "deepseek-chat").strip()
        if api_key or "deepseek" in base_url.lower() or base_url != "https://api.openai.com/v1":
            logger.info("Agent V2: using cloud config — %s @ %s", cloud_model, base_url)
            return OpenAiCompatProvider(base_url=base_url, api_key=api_key, model=model or cloud_model)

    # 4. 兜底：本地 Ollama
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").strip()
    logger.info("Agent V2: falling back to Ollama — %s", model or "qwen3:8b")
    return OpenAiCompatProvider(base_url=ollama_base, api_key="", model=model or "qwen3:8b")


def _build_system_prompt(workspace_root: str, tools: list) -> str:
    tool_list = ", ".join(t.name for t in tools)
    return (
        f"You are Scholar Assistant, an academic AI writing assistant.\n"
        f"Workspace: {workspace_root}\n"
        f"Available tools: {tool_list}\n\n"
        "CRITICAL RULES — you MUST follow these:\n"
        "1. NEVER just describe what you would do — actually DO it with tools.\n"
        "2. 'Read/查看/读' → immediately call read_file. Do NOT ask 'should I read?'\n"
        "3. 'Write/保存/创建/写' → call write_file with the content.\n"
        "4. 'Modify/改/替换' → call str_replace.\n"
        "5. 'Run/运行/执行' → call run_command with the command.\n"
        "6. 'Search/找' → call grep_files or glob_files.\n"
        "7. After each tool, use its result to decide the next action.\n"
        "8. Respond concisely in the same language as the user.\n"
        "9. Do NOT ask for confirmation before acting — just DO it.\n"
    )


def _create_runtime(workspace_root: str, session_id: str = "") -> ConversationRuntime:
    provider = _create_provider()
    ws = Path(workspace_root) if workspace_root else Path.cwd()
    registry = create_default_registry(workspace_root=ws)
    register_academic_tools(registry)
    policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())

    sid = session_id or f"sess_{int(time.time() * 1000) % 10_000_000:07d}"
    session = Session(workspace=str(ws), model=provider.model, session_id=sid)
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session._save_path = str(_SESSION_DIR / f"{session.session_id}.jsonl")

    sp = _build_system_prompt(str(ws), registry.definitions())
    return ConversationRuntime(provider=provider, tool_registry=registry,
                                permission_policy=policy, session=session,
                                system_prompt=sp, auto_approve=False)


async def _cleanup_pool():
    """Remove stale sessions."""
    now = time.monotonic()
    stale = []
    async with _SESSION_LOCK:
        for sid, rt in _SESSION_POOL.items():
            # Stale if older than 1 hour and not the only session
            pass  # Simple cleanup — don't auto-evict unless requested
    return len(stale)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_agent_v2_routes(app: FastAPI, prefix: str = "/api/agent/v2") -> None:

    @app.post(f"{prefix}/chat")
    async def v2_chat(req: ChatRequestV2, request: Request):
        """主对话端点 — SSE 流式。"""
        workspace = req.workspace_root or ""

        async def _stream() -> AsyncGenerator[dict, None]:
            rt = None
            try:
                rt = _create_runtime(workspace)
                sid = rt.session.session_id
                async with _SESSION_LOCK:
                    _SESSION_POOL[sid] = rt
                async for event in rt.turn(req.message):
                    yield agent_event_to_sse_stream(event)
            except Exception as e:
                logger.exception("V2 chat error")
                yield {"event": "error",
                       "data": json.dumps({"type": "error", "content": f"Agent error: {e}", "event_id": "err_0001"}, ensure_ascii=False)}
            finally:
                if rt:
                    async with _SESSION_LOCK:
                        _SESSION_POOL.pop(rt.session.session_id, None)

        from sse_starlette.sse import EventSourceResponse
        return EventSourceResponse(_stream(), media_type="text/event-stream")

    @app.post(f"{prefix}/approve/{{session_id}}/{{event_id}}")
    async def v2_approve(session_id: str, event_id: str, req: ApproveRequest, request: Request):
        """审批工具调用 — 决定后 SSE 流恢复执行。"""
        async with _SESSION_LOCK:
            rt = _SESSION_POOL.get(session_id)
        if rt is None:
            raise HTTPException(404, f"Session {session_id} not found or expired")
        decision = req.decision if isinstance(req.decision, str) else getattr(req.decision, 'value', 'deny')
        ok = rt.approve(event_id, decision)
        if not ok:
            raise HTTPException(400, f"Approval event {event_id} not found (already processed or timed out)")
        logger.info("approve: session=%s event=%s decision=%s", session_id, event_id, decision)
        return {"status": "ok", "session_id": session_id, "decision": decision}

    @app.post(f"{prefix}/abort/{{session_id}}")
    async def v2_abort(session_id: str, request: Request):
        """中止会话 — 释放所有等待中的审批。"""
        async with _SESSION_LOCK:
            rt = _SESSION_POOL.pop(session_id, None)
        if rt is None:
            raise HTTPException(404, f"Session {session_id} not found")
        rt.abort()
        return {"status": "ok", "aborted": session_id}

    @app.get(f"{prefix}/sessions")
    async def v2_list_sessions(request: Request):
        """列出所有活跃会话。"""
        async with _SESSION_LOCK:
            result = [{"id": sid, "state": "active", "workspace": rt.session.meta.workspace,
                       "model": rt.session.meta.model, "messages": rt.session.message_count}
                      for sid, rt in _SESSION_POOL.items()]
        # Also list persisted sessions
        if _SESSION_DIR.exists():
            for f in sorted(_SESSION_DIR.glob("*.jsonl"), reverse=True)[:20]:
                fid = f.stem
                if not any(s["id"] == fid for s in result):
                    result.append({"id": fid, "state": "persisted", "workspace": "", "model": "", "messages": 0})
        return result

    @app.post(f"{prefix}/resume/{{session_id}}")
    async def v2_resume(session_id: str, request: Request):
        """恢复会话 — 加载持久化 session 并继续。"""
        session_path = _SESSION_DIR / f"{session_id}.jsonl"
        if not session_path.is_file():
            raise HTTPException(404, f"Session {session_id} not found")

        loaded = Session.load(session_path)
        workspace = loaded.meta.workspace or ""

        async def _stream() -> AsyncGenerator[dict, None]:
            rt = None
            try:
                provider = _create_provider()
                ws = Path(workspace) if workspace else Path.cwd()
                registry = create_default_registry(workspace_root=ws)
                policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
                loaded._save_path = str(session_path)
                sp = _build_system_prompt(str(ws), registry.definitions())
                rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=loaded, system_prompt=sp)
                async with _SESSION_LOCK:
                    _SESSION_POOL[session_id] = rt
                # Emit session start + restore info for the frontend
                from src.agent_v2.types import AgentEvent
                yield agent_event_to_sse_stream(AgentEvent.session_started(session_id))
                yield {"event": "response", "data": json.dumps(
                    {"type": "response", "content": f"Session {session_id} restored ({loaded.message_count} messages)."}, ensure_ascii=False)}
                yield {"event": "done", "data": json.dumps({"type": "done", "metadata": {"session_id": session_id}}, ensure_ascii=False)}
            except Exception as e:
                logger.exception("V2 resume error")
                yield {"event": "error", "data": json.dumps({"type": "error", "content": f"Resume error: {e}", "event_id": "err_resume"}, ensure_ascii=False)}
            finally:
                if rt:
                    async with _SESSION_LOCK:
                        _SESSION_POOL.pop(session_id, None)

        from sse_starlette.sse import EventSourceResponse
        return EventSourceResponse(_stream(), media_type="text/event-stream")

    @app.get(f"{prefix}/tools")
    async def v2_list_tools(request: Request):
        """列出可用工具。"""
        ws = request.query_params.get("workspace_root", "")
        registry = create_default_registry(workspace_root=ws)
        return [{"name": d.name, "description": d.description, "input_schema": d.input_schema}
                for d in registry.definitions()]

    # Workflow stubs (保持前端兼容)
    @app.get(f"{prefix}/workflows/{{workflow_id}}/messages")
    async def v2_workflow_messages(workflow_id: str):
        return []

    @app.post(f"{prefix}/workflows/cleanup")
    async def v2_workflow_cleanup():
        return {"status": "ok"}

    @app.delete(f"{prefix}/workflows/{{workflow_id}}")
    async def v2_workflow_delete(workflow_id: str):
        return {"status": "ok", "deleted": workflow_id}

    @app.get(f"{prefix}/health")
    async def v2_health():
        async with _SESSION_LOCK:
            active = len(_SESSION_POOL)
        return {"status": "ok", "version": "0.4.0", "runtime": "ConversationRuntime", "active_sessions": active}
