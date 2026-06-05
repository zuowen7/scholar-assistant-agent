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
from src.agent_v2.runtime.usage import UsageTracker
from src.agent_v2.sse_adapter import agent_event_to_sse_stream
from src.agent_v2.tools.registry import create_default_registry
from src.agent_v2.tools.academic_tools import register_academic_tools
from src.agent_v2.tools.sub_agent import register_sub_agent
from src.agent_v2.skills import SkillRegistry, _BUILTIN_SKILLS
from src.agent_v2.hooks import HookRunner, HookEvent, HookPoint
from src.agent_v2.plugins import PluginManager, create_default_plugin_manager
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


def _load_agent_config() -> dict:
    """读取 agent 配置段（合并 default.yaml + local.yaml + env override）。

    优先级: env var > config/local.yaml > config/default.yaml
    """
    import yaml
    _python_root = Path(__file__).resolve().parent.parent.parent
    merged = {}

    for cfg_name in ("config/default.yaml", "config/default.local.yaml"):
        cfg_path = _python_root / cfg_name
        if cfg_path.is_file():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    _deep_merge(merged, yaml.safe_load(f) or {})
            except Exception:
                pass

    agent_cfg = merged.get("agent", {})

    # Env var overrides
    if os.environ.get("ANTHROPIC_API_KEY"):
        agent_cfg["provider"] = "anthropic"
        agent_cfg["api_key"] = os.environ["ANTHROPIC_API_KEY"]
        agent_cfg["base_url"] = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    if os.environ.get("OPENAI_API_KEY"):
        agent_cfg["provider"] = "openai"
        agent_cfg["api_key"] = os.environ["OPENAI_API_KEY"]
        agent_cfg["base_url"] = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if os.environ.get("AGENT_MODEL"):
        agent_cfg["model"] = os.environ["AGENT_MODEL"]

    return agent_cfg


def _resolve_model_alias(model: str, aliases: dict) -> str:
    """解析模型别名。参考 claw-code resolve_model_alias。别名从 config 读取。"""
    return aliases.get(model.lower(), model)


def _create_provider():
    from src.agent_v2.providers.openai_compat import OpenAiCompatProvider

    cfg = _load_agent_config()
    aliases = cfg.get("model_aliases", {})
    model = _resolve_model_alias(cfg.get("model", "").strip(), aliases)
    provider = cfg.get("provider", "auto").strip().lower()
    api_key = cfg.get("api_key", "").strip()
    base_url = cfg.get("base_url", "").strip()
    translator_cloud = _load_cloud_config()

    # 1. Explicit provider from config
    if provider == "anthropic" and api_key:
        logger.info("Agent V2: config[agent].provider=anthropic — %s", model or "claude-sonnet-4-6")
        return OpenAiCompatProvider(
            base_url=base_url or "https://api.anthropic.com",
            api_key=api_key, model=model or "claude-sonnet-4-6")

    if provider == "openai" and (api_key or base_url):
        logger.info("Agent V2: config[agent].provider=openai — %s @ %s",
                     model or "gpt-4o", base_url or "https://api.openai.com/v1")
        return OpenAiCompatProvider(
            base_url=base_url or "https://api.openai.com/v1",
            api_key=api_key, model=model or "gpt-4o")

    # 2. API key without explicit provider — detect from key prefix
    if api_key:
        if api_key.startswith("sk-ant-"):
            logger.info("Agent V2: Anthropic key detected — %s", model or "claude-sonnet-4-6")
            return OpenAiCompatProvider(
                base_url=base_url or "https://api.anthropic.com",
                api_key=api_key, model=model or "claude-sonnet-4-6")
        logger.info("Agent V2: OpenAI-compatible key — %s", model or "gpt-4o")
        return OpenAiCompatProvider(
            base_url=base_url or "https://api.openai.com/v1",
            api_key=api_key, model=model or "gpt-4o")

    # 3. Fallback: translator cloud config (DeepSeek etc.)
    if translator_cloud:
        tk = translator_cloud.get("api_key", "").strip()
        tb = translator_cloud.get("base_url", "").strip()
        tm = translator_cloud.get("model", "").strip()
        if tk or tb:
            tb = tb or "https://api.deepseek.com/v1"
            m = model or tm or "deepseek-chat"
            logger.info("Agent V2: cloud config — %s @ %s", m, tb)
            return OpenAiCompatProvider(base_url=tb, api_key=tk, model=m)

    # 4. Local Ollama
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").strip()
    m = model or "qwen3:8b"
    logger.info("Agent V2: Ollama — %s", m)
    return OpenAiCompatProvider(base_url=ollama_base, api_key="", model=m)


def _build_system_prompt(workspace_root: str, tools: list) -> str:
    tool_list = ", ".join(t.name for t in tools)
    return (
        f"You are Scholar Assistant, an academic AI writing assistant. "
        f"You help users with academic writing, translation, editing, and research tasks.\n\n"
        f"# Environment\n"
        f"Working directory: {workspace_root}\n"
        f"Available tools: {tool_list}\n\n"
        f"# Using tools\n"
        f"Tools help you read, write, and modify files in the workspace. "
        f"When you need to see a file's contents, use read_file. "
        f"When you need to modify a file, use str_replace or write_file. "
        f"When you need to search, use grep_files or glob_files. "
        f"Each tool result will be shown to you so you can decide the next step.\n\n"
        f"# Task execution\n"
        f"Read files before modifying them. Keep changes focused on what was asked. "
        f"If you need to expand a document, work section by section using str_replace — "
        f"this shows progress to the user and avoids long waits. "
        f"After each change, the file tree and editor will refresh automatically.\n\n"
        f"# Communication\n"
        f"Respond in the same language as the user. "
        f"Be concise — for simple tasks, one tool call and a short confirmation is enough.\n"
    )


def _create_runtime(workspace_root: str, session_id: str = "") -> ConversationRuntime:
    provider = _create_provider()
    ws = Path(workspace_root) if workspace_root else Path.cwd()

    # Tool registry
    registry = create_default_registry(workspace_root=ws)
    register_academic_tools(registry)
    register_sub_agent(registry)
    registry._provider = provider

    # Skills
    skill_registry = SkillRegistry()
    for s in _BUILTIN_SKILLS:
        skill_registry.register(s)
    # Load user skills from data/agent_v2/skills/
    _skills_dir = Path(__file__).resolve().parent.parent.parent / "data" / "agent_v2" / "skills"
    skill_registry.load_dir(_skills_dir)

    # Hooks
    hook_runner = HookRunner()
    hook_runner.add_builtin_hooks()

    # Plugins
    plugin_mgr = create_default_plugin_manager()
    plugin_mgr.apply_all(skill_registry, hook_runner, registry)

    # Policy
    policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())

    sid = session_id or f"sess_{int(time.time() * 1000) % 10_000_000:07d}"
    session = Session(workspace=str(ws), model=provider.model, session_id=sid)
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session._save_path = str(_SESSION_DIR / f"{session.session_id}.jsonl")

    # System prompt with skill injection
    base_prompt = _build_system_prompt(str(ws), registry.definitions())
    skill_prompt = skill_registry.build_prompt_injection(layer="agents")
    sp = base_prompt + "\n" + skill_prompt if skill_prompt else base_prompt

    return ConversationRuntime(provider=provider, tool_registry=registry,
                                permission_policy=policy, session=session,
                                system_prompt=sp, auto_approve=True)


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

    @app.get(f"{prefix}/cost/{{session_id}}")
    async def v2_cost(session_id: str, request: Request):
        """会话成本统计。"""
        async with _SESSION_LOCK:
            rt = _SESSION_POOL.get(session_id)
        if rt is not None:
            return rt.usage.to_dict()
        # Try persisted session
        session_path = _SESSION_DIR / f"{session_id}.jsonl"
        if session_path.is_file():
            loaded = Session.load(session_path)
            usage = UsageTracker(model=loaded.meta.model)
            for msg in loaded.messages:
                if msg.usage:
                    usage.record(msg.usage)
            return usage.to_dict()
        raise HTTPException(404, f"Session {session_id} not found")

    @app.get(f"{prefix}/skills")
    async def v2_skills(request: Request):
        """列出所有 skills + 激活状态。"""
        skill_registry = SkillRegistry()
        for s in _BUILTIN_SKILLS:
            skill_registry.register(s)
        _sdir = Path(__file__).resolve().parent.parent.parent / "data" / "agent_v2" / "skills"
        skill_registry.load_dir(_sdir)
        plugin_mgr = create_default_plugin_manager()
        plugin_mgr.register_skills(skill_registry)
        return skill_registry.list_all()

    @app.get(f"{prefix}/plugins")
    async def v2_plugins(request: Request):
        """列出所有插件 + 启用状态。"""
        plugin_mgr = create_default_plugin_manager()
        return plugin_mgr.list_all()

    @app.get(f"{prefix}/config")
    async def v2_config(request: Request):
        """返回当前 agent 配置（脱敏）。"""
        cfg = _load_agent_config()
        aliases = cfg.get("model_aliases", {})
        return {
            "model": cfg.get("model", ""),
            "provider": cfg.get("provider", "auto"),
            "base_url": cfg.get("base_url", ""),
            "has_api_key": bool(cfg.get("api_key", "").strip()),
            "model_aliases": aliases,
            "available_aliases": list(aliases.keys()),
        }

    @app.get(f"{prefix}/health")
    async def v2_health():
        async with _SESSION_LOCK:
            active = len(_SESSION_POOL)
        return {"status": "ok", "version": "0.4.0", "runtime": "ConversationRuntime", "active_sessions": active}
