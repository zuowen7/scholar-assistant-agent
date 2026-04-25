"""FastAPI 应用工厂 — 本地(Ollama+云) 与 纯云端 两种模式"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.parser import extract_document, SUPPORTED_EXTENSIONS
from src.cleaner import clean_text_full
from src.chunker import chunk_text_full
from src.formatter import format_output
from src.translator.ollama_client import OllamaClient, TranslationResult
from src.translator.cloud_client import CloudClient, PROVIDER_PRESETS
from src.translator.context import extract_document_context

# Agent 子系统 (延迟导入，chromadb 未安装时不影响翻译功能)
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
    _AGENT_AVAILABLE = True
except ImportError:
    _AGENT_AVAILABLE = False


def _is_frozen() -> bool:
    """检测是否运行在 PyInstaller 打包环境中"""
    return getattr(__import__("sys"), "frozen", False) and hasattr(__import__("sys"), "_MEIPASS")


# BUNDLED_DIR: 只读资源目录（PyInstaller 的 _MEIPASS 或源码目录）
# RUNTIME_DIR: 可读写目录（api.exe 旁或源码目录），用于配置文件和数据存储
if _is_frozen():
    import sys as _sys
    BUNDLED_DIR = Path(_sys._MEIPASS)
    RUNTIME_DIR = Path(_sys.executable).parent
else:
    BUNDLED_DIR = Path(__file__).parent
    RUNTIME_DIR = Path(__file__).parent

BASE_DIR = RUNTIME_DIR
DOCKER_MODE = os.environ.get("DOCKER_MODE", "").lower() in ("1", "true", "yes")
CONFIG_PATH = (RUNTIME_DIR / "config" / "docker.yaml") if DOCKER_MODE else (RUNTIME_DIR / "config" / "default.yaml")

# PyInstaller 打包环境下，首次运行时从 bundle 复制默认配置到运行时目录
if _is_frozen() and not DOCKER_MODE and not CONFIG_PATH.exists():
    bundled_default = BUNDLED_DIR / "config" / "default.yaml"
    if bundled_default.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_default, CONFIG_PATH)

logger = logging.getLogger(__name__)

MAX_TASKS = 10
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB


class ConfigUpdate(BaseModel):
    chunker: dict | None = None
    translator: dict | None = None
    formatter: dict | None = None
    cloud: dict | None = None


class FilePathPayload(BaseModel):
    path: str


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None
    context_text: str | None = None  # 引用上下文（选中文本、文档片段等）
    constraints: str | None = None    # 追加约束（格式、风格、字数限制等）


class RAGIngestRequest(BaseModel):
    doc_id: str
    text: str
    title: str = ""


class WordExportRequest(BaseModel):
    content: str   # Markdown 格式文本
    title: str = "Scholar Assistant Export"


class EditRequest(BaseModel):
    text: str = ""
    instruction: str = ""
    task_type: str | None = None
    previous: str | None = None


class CompletionRequest(BaseModel):
    context: str = ""
    max_tokens: int = 128


class MarkdownExportRequest(BaseModel):
    markdown: str = ""
    template_id: str = "generic_article"
    title: str | None = None


class ComplianceRequest(BaseModel):
    markdown: str = ""
    title: str = ""
    venue: str = ""
    required_sections: str = ""


class PaperScaffoldRequest(BaseModel):
    template_id: str = "generic_article"
    title: str = ""
    sections: list[str] | None = None


class PaperStyleTransferRequest(BaseModel):
    text: str = ""
    template_id: str = "generic_article"
    section: str = "introduction"


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


_config_cache: dict | None = None
_config_cache_mtime: float = 0.0


def _load_config() -> dict:
    global _config_cache, _config_cache_mtime
    if CONFIG_PATH.exists():
        mtime = CONFIG_PATH.stat().st_mtime
        if _config_cache is not None and mtime == _config_cache_mtime:
            return copy.deepcopy(_config_cache)
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
            _config_cache_mtime = mtime
            return copy.deepcopy(_config_cache)
    return {}


def _save_config(config: dict) -> None:
    global _config_cache, _config_cache_mtime
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    _config_cache = copy.deepcopy(config)
    _config_cache_mtime = CONFIG_PATH.stat().st_mtime


def _build_cloud_client(trans_cfg: dict, cloud_cfg: dict) -> CloudClient:
    return CloudClient(
        provider=cloud_cfg.get("provider", "openai"),
        base_url=cloud_cfg.get("base_url", "https://api.openai.com/v1"),
        api_key=cloud_cfg.get("api_key", ""),
        model=cloud_cfg.get("model", "gpt-4o"),
        temperature=trans_cfg.get("temperature", 0.3),
        max_tokens=cloud_cfg.get("max_tokens", 16384),
        system_prompt=trans_cfg.get("system_prompt", ""),
        timeout=trans_cfg.get("timeout", 300.0),
    )


def _mask_api_key(config: dict) -> None:
    cloud_cfg = config.get("translator", {}).get("cloud", {})
    api_key = cloud_cfg.get("api_key", "")
    if api_key and len(api_key) > 8:
        cloud_cfg["api_key"] = api_key[:4] + "****" + api_key[-4:]


def _is_masked(value: str) -> bool:
    return "****" in value


_DENIED_PATH_PREFIXES = (
    "/etc", "/proc", "/sys", "/dev", "/root",
    "C:\\Windows", "C:\\Program Files",
)

_DENIED_EXTENSIONS = {".env", ".key", ".pem", ".p12", ".pfx", ".secret", ".credentials"}


def _validate_file_path(file_path: Path) -> None:
    """防止路径遍历: 禁止访问系统敏感目录和敏感文件类型"""
    resolved = str(file_path)
    for prefix in _DENIED_PATH_PREFIXES:
        if resolved.startswith(prefix):
            raise HTTPException(403, f"禁止访问系统目录: {prefix}")
    if file_path.suffix.lower() in _DENIED_EXTENSIONS:
        raise HTTPException(403, f"禁止访问敏感文件: {file_path.suffix}")
    # 禁止隐藏文件
    if file_path.name.startswith("."):
        raise HTTPException(403, "禁止访问隐藏文件")


def create_app(*, cloud_only: bool = False) -> FastAPI:
    """创建 FastAPI 应用。

    cloud_only=True：翻译管道仅使用云端大模型，不连接 Ollama；数据目录使用 ``data_cloud/``，避免与本地实例混用。
    """
    tasks: dict[str, dict] = {}
    _busy_lock = asyncio.Lock()

    data_root = RUNTIME_DIR / ("data_cloud" if cloud_only else "data")
    input_dir = data_root / "input"
    output_dir = data_root / "output"

    def _cleanup_tasks() -> None:
        done_ids = [tid for tid, t in tasks.items() if t["status"] in ("done", "error")]
        if len(done_ids) <= MAX_TASKS:
            return
        excess = len(done_ids) - MAX_TASKS
        for tid in done_ids[:excess]:
            del tasks[tid]

    _app_title = "Scholar Assistant API (cloud-only)" if cloud_only else "Scholar Assistant API"
    parser = argparse.ArgumentParser(description=_app_title)
    app = FastAPI(title=_app_title, version="0.4.2")

        # ── 全局异常处理 ──

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """捕获所有未处理异常，返回统一格式 JSON，避免前端收到 500 纯文本"""
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"服务器内部错误: {exc}"},
        )

    allowed_origins = [
        "http://localhost",
        "http://localhost:5173",
        "http://localhost:18088",
        "http://localhost:18089",
        "http://127.0.0.1:18088",
        "http://127.0.0.1:18089",
        "tauri://localhost",
        "https://tauri.localhost",
        "http://tauri.localhost",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/api/health")
    def health():
        payload = {"status": "ok", "version": "0.4.2"}
        if cloud_only:
            payload["mode"] = "cloud_only"
        return payload

    @app.get("/api/ollama/status")
    def ollama_status():
        if cloud_only:
            return {
                "reachable": False,
                "disabled": True,
                "message": "当前为纯云端模式，不使用 Ollama",
            }
        config = _load_config()
        trans_cfg = config.get("translator", {})
        client = OllamaClient(
            base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
        )
        try:
            return {"reachable": client.health_check()}
        finally:
            client.close()

    @app.get("/api/cloud/status")
    def cloud_status():
        config = _load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        if not cloud_cfg.get("api_key"):
            return {"reachable": False, "error": "未配置 API Key"}
        client = _build_cloud_client(trans_cfg, cloud_cfg)
        reachable = client.health_check()
        return {"reachable": reachable}

    @app.get("/api/cloud/providers")
    def cloud_providers():
        return PROVIDER_PRESETS

    @app.post("/api/translate")
    async def start_translate(file: UploadFile = File(...)):
        if not _busy_lock.locked():
            await _busy_lock.acquire()
        else:
            raise HTTPException(409, "已有翻译任务在运行，请等待完成")

        if not file.filename:
            raise HTTPException(400, "文件名不能为空")
        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
            raise HTTPException(400, f"不支持的文件格式: {ext}。支持: {supported}")

        task_id = uuid.uuid4().hex[:8]
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        input_file = input_dir / f"{task_id}_{file.filename}"
        with open(input_file, "wb") as f:
            total = 0
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    f.close()
                    input_file.unlink(missing_ok=True)
                    raise HTTPException(413, "文件过大，最大支持 200 MB")
                f.write(chunk)

        tasks[task_id] = {
            "status": "pending",
            "input_path": str(input_file),
            "output_path": None,
            "content": None,
            "error": None,
        }

        return {"task_id": task_id}

    @app.post("/api/translate/path")
    async def start_translate_path(payload: FilePathPayload):
        if not _busy_lock.locked():
            await _busy_lock.acquire()
        else:
            raise HTTPException(409, "已有翻译任务在运行，请等待完成")

        file_path = Path(payload.path).resolve()
        # 路径遍历防护: 禁止访问敏感目录
        _validate_file_path(file_path)
        if not file_path.exists():
            raise HTTPException(400, "文件不存在")
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
            raise HTTPException(400, f"不支持的文件格式: {file_path.suffix}。支持: {supported}")
        if file_path.stat().st_size > MAX_UPLOAD_SIZE:
            raise HTTPException(413, "文件过大，最大支持 200 MB")

        task_id = uuid.uuid4().hex[:8]
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        in_path = input_dir / f"{task_id}_{file_path.name}"
        shutil.copy2(file_path, in_path)

        tasks[task_id] = {
            "status": "pending",
            "input_path": str(in_path),
            "output_path": None,
            "content": None,
            "error": None,
        }

        return {"task_id": task_id}

    async def _run_pipeline(task_id: str) -> AsyncGenerator[dict, None]:
        """翻译管道 generator — 不持有 _busy_lock，由 translate_stream 管理。"""
        task = tasks[task_id]
        task["status"] = "running"

        try:
            config = _load_config()
            input_path = task["input_path"]

            ext = Path(input_path).suffix.lower()
            fmt_name = SUPPORTED_EXTENSIONS.get(ext, "文档")
            yield {
                "event": "progress",
                "data": json.dumps({"step": 1, "total": 5, "message": f"解析 {fmt_name}..."}),
            }
            doc = await asyncio.to_thread(extract_document, input_path)
            raw_text = doc.full_text
            dual_pages = sum(1 for p in doc.pages if getattr(p, "is_dual_column", False))
            yield {
                "event": "parsed",
                "data": json.dumps({
                    "pages": doc.page_count,
                    "chars": len(raw_text),
                    "dual_column_pages": dual_pages,
                }),
            }

            yield {
                "event": "progress",
                "data": json.dumps({"step": 2, "total": 5, "message": "清洗文本..."}),
            }
            clean_result = await asyncio.to_thread(clean_text_full, raw_text)
            yield {
                "event": "cleaned",
                "data": json.dumps({
                    "chars": len(clean_result.text),
                    "has_references": clean_result.has_references,
                }),
            }

            yield {
                "event": "progress",
                "data": json.dumps({"step": 3, "total": 5, "message": "切块..."}),
            }
            chunker_cfg = config.get("chunker", {})
            chunk_result = await asyncio.to_thread(
                chunk_text_full,
                clean_result.text,
                chunker_cfg.get("max_tokens", 2048),
                chunker_cfg.get("overlap_tokens", 128),
                chunker_cfg.get("strategy", "sentence"),
                True,
            )
            yield {
                "event": "chunked",
                "data": json.dumps({
                    "total_chunks": len(chunk_result.chunks),
                    "references_chars": len(chunk_result.references_text),
                }),
            }

            yield {
                "event": "progress",
                "data": json.dumps({"step": 4, "total": 5, "message": "翻译中..."}),
            }
            trans_cfg = config.get("translator", {})
            use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"

            if use_cloud:
                cloud_cfg = trans_cfg.get("cloud", {})
                key = (cloud_cfg.get("api_key") or "").strip()
                if not key:
                    raise ValueError(
                        "未配置云端 API Key：请在配置中设置 translator.cloud.api_key，"
                        "或在前端「翻译引擎 → 云端 API」中填写并保存。"
                    )
                client = _build_cloud_client(trans_cfg, cloud_cfg)
            else:
                ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get(
                    "ollama_base_url", "http://localhost:11434"
                )
                client = OllamaClient(
                    base_url=ollama_url,
                    model=trans_cfg.get("model", "qwen3:8b"),
                    temperature=trans_cfg.get("temperature", 0.3),
                    num_predict=trans_cfg.get("num_predict", 16384),
                    system_prompt=trans_cfg.get("system_prompt", ""),
                    timeout=trans_cfg.get("timeout", 300.0),
                )

            doc_context = extract_document_context(raw_text)
            if doc_context:
                client.set_document_context(doc_context)

            results = []
            try:
                total_chunks = len(chunk_result.chunks)
                for i, chunk in enumerate(chunk_result.chunks):
                    prev_trans = results[-1].translated if results else ""
                    try:
                        result = await asyncio.to_thread(client.translate, chunk.text, prev_trans)
                    except Exception as e:
                        logger.warning("块 %d/%d 翻译失败，尝试单独重试: %s", i + 1, total_chunks, e)
                        # 重试前给 GPU/API 喘息时间
                        await asyncio.sleep(2.0)
                        try:
                            result = await asyncio.to_thread(client.translate, chunk.text, prev_trans)
                        except Exception as e2:
                            logger.error("块 %d/%d 重试仍失败: %s，保留原文", i + 1, total_chunks, e2)
                            result = TranslationResult(
                                original=chunk.text,
                                translated=chunk.text,
                                model="",
                            )
                            yield {
                                "event": "chunk_error",
                                "data": json.dumps({
                                    "index": i,
                                    "total": total_chunks,
                                    "error": str(e2),
                                }),
                            }
                    results.append(result)
                    # 每个 chunk 之间让出事件循环，给 GPU 显存回收时间
                    await asyncio.sleep(0.1)
                    yield {
                        "event": "chunk_done",
                        "data": json.dumps({
                            "index": i,
                            "total": total_chunks,
                            "original_preview": result.original[:200],
                            "translated_preview": result.translated[:200],
                            "tokens": result.completion_tokens,
                            "fallback": result.original == result.translated,
                        }),
                    }
            finally:
                if hasattr(client, "close"):
                    client.close()

            yield {
                "event": "progress",
                "data": json.dumps({"step": 5, "total": 5, "message": "生成输出..."}),
            }
            fmt_cfg = config.get("formatter", {})
            content = format_output(
                results,
                output_format=fmt_cfg.get("output_format", "bilingual"),
            )

            out_path = output_dir / f"{task_id}_translated.md"
            out_path.write_text(content, encoding="utf-8")

            task["status"] = "done"
            task["output_path"] = str(out_path)

            yield {
                "event": "complete",
                "data": json.dumps({
                    "task_id": task_id,
                    "output_path": str(out_path),
                    "content": content,
                    "chunks": [
                        {"original": r.original, "translated": r.translated}
                        for r in results
                    ],
                }),
            }

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}),
            }
        finally:
            input_file = task.get("input_path")
            if input_file:
                try:
                    Path(input_file).unlink(missing_ok=True)
                except OSError:
                    pass
            _cleanup_tasks()

    @app.get("/api/translate/{task_id}/stream")
    async def translate_stream(task_id: str):
        if task_id not in tasks:
            raise HTTPException(404, f"任务 {task_id} 不存在")

        t = tasks[task_id]
        if t["status"] == "running":
            raise HTTPException(409, "该任务已在运行中")

        if not _busy_lock.locked():
            raise HTTPException(409, "未持有任务锁，请先通过 POST /api/translate 创建任务")
        pipeline = _run_pipeline(task_id)

        async def _wrapped() -> AsyncGenerator[dict, None]:
            try:
                async for event in pipeline:
                    yield event
            finally:
                _busy_lock.release()

        return EventSourceResponse(
            _wrapped(),
            media_type="text/event-stream",
        )

    @app.get("/api/config")
    def get_config():
        config = copy.deepcopy(_load_config())
        if cloud_only:
            config.setdefault("translator", {})["engine"] = "cloud"
        _mask_api_key(config)
        return config

    @app.put("/api/config")
    def update_config(cfg: ConfigUpdate):
        current = _load_config()
        for section in ["chunker", "translator", "formatter"]:
            val = getattr(cfg, section)
            if val:
                current[section] = {**current.get(section, {}), **val}
        if cfg.cloud:
            trans = current.setdefault("translator", {})
            existing_cloud = trans.get("cloud", {})
            new_api_key = cfg.cloud.get("api_key", "")
            if new_api_key and _is_masked(new_api_key):
                cfg.cloud["api_key"] = existing_cloud.get("api_key", "")
            trans["cloud"] = {**existing_cloud, **cfg.cloud}
        if cloud_only:
            current.setdefault("translator", {})["engine"] = "cloud"
        _save_config(current)
        out = copy.deepcopy(current)
        _mask_api_key(out)
        if cloud_only:
            out.setdefault("translator", {})["engine"] = "cloud"
        return out

    @app.get("/api/download/{task_id}")
    def download_result(task_id: str):
        if task_id not in tasks:
            raise HTTPException(404, "任务不存在")
        t = tasks[task_id]
        if t["status"] != "done" or not t.get("output_path"):
            raise HTTPException(400, "翻译尚未完成")
        path = Path(t["output_path"])
        if not path.exists():
            raise HTTPException(404, "文件已丢失")
        return FileResponse(
            path,
            filename=f"{task_id}_translated.md",
            media_type="text/markdown",
        )

    # ── Agent / RAG 端点 ──────────────────────────────────────────────

    _agent_instance: AgentLoop | None = None
    _rag_store: RAGStore | None = None
    _agent_lock = asyncio.Lock()

    async def _get_agent() -> AgentLoop:
        """懒加载 Agent 单例 — 首次请求时初始化，复用配置。"""
        nonlocal _agent_instance, _rag_store

        if _agent_instance is not None:
            return _agent_instance

        async with _agent_lock:
            if _agent_instance is not None:
                return _agent_instance

            config = _load_config()
            agent_cfg = config.get("agent", {})
            trans_cfg = config.get("translator", {})

            # 初始化 RAG 存储
            rag_cfg = agent_cfg.get("rag", {})
            rag_dir = RUNTIME_DIR / rag_cfg.get("persist_dir", "data/chromadb")
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

            # 初始化工具注册表
            use_cloud_tools = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            cloud_cfg_tools = trans_cfg.get("cloud", {}) if use_cloud_tools else {}
            registry = create_default_registry(
                rag_store=_rag_store,
                ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                model=agent_cfg.get("model", "qwen3:8b"),
                cloud_base_url=cloud_cfg_tools.get("base_url", "https://api.openai.com/v1") if use_cloud_tools else "",
                cloud_api_key=(cloud_cfg_tools.get("api_key") or "").strip() if use_cloud_tools else "",
                cloud_model=cloud_cfg_tools.get("model", "gpt-4o") if use_cloud_tools else "",
            )

            # 可选: 初始化时分复用调度器
            scheduler = None
            vram_cfg = agent_cfg.get("vram", {})
            if vram_cfg.get("enabled", True) and not cloud_only:
                scheduler = MultiplexingScheduler(
                    ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                    model=agent_cfg.get("model", "qwen3:8b"),
                )

            # Phase 1/2/3: 上下文工程 + 记忆 + Skill + 轨迹
            agent_data_dir = str(data_root / "agent")
            memory_manager = MemoryManager(data_dir=agent_data_dir)
            skill_registry = SkillRegistry(skills_dir=agent_data_dir + "/skills")
            trajectory_recorder = TrajectoryRecorder(data_dir=agent_data_dir + "/trajectories")

            ollama_url = trans_cfg.get("ollama_base_url", "http://localhost:11434")
            agent_model = agent_cfg.get("model", "qwen3:8b")
            compressor = ContextCompressor(
                max_window_tokens=agent_cfg.get("max_window_tokens", 32_000),
                threshold_percent=agent_cfg.get("compress_threshold", 0.50),
                ollama_base_url=ollama_url,
                summary_model=agent_model,
            )
            prompt_builder = PromptBuilder(tool_registry=registry)

            # 双引擎: 用户设置 engine=cloud 且有 api_key 时走云端, 否则走 Ollama
            use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            if use_cloud:
                cloud_cfg = trans_cfg.get("cloud", {})
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
                api_format=cloud_cfg.get("provider", "openai") if use_cloud else "openai",
                memory_dir=agent_data_dir + "/memory",
            )

            logger.info("Agent 初始化完成 (model=%s, rag=%s)",
                        agent_cfg.get("model"), rag_dir)
            return _agent_instance

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        """Agent 对话端点 — SSE 流式返回 ReAct 推理过程。

        支持 Ollama 和云端双引擎。
        增强功能：
        - context_text: 传入选中文本、文档片段作为上下文
        - constraints: 传入格式/风格/字数等追加约束
        - 这些内容会被拼接进用户消息前，引导 Agent 精准回答
        """
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装，请安装 chromadb")

        agent = await _get_agent()

        # 将历史消息转换为 Message 对象
        history: list[Message] | None = None
        if req.history:
            history = [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in req.history
            ]

        # 增强消息：注入上下文文本和追加约束
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
        """列出 RAG 知识库中的所有文档。"""
        if _rag_store is None:
            return []
        docs = _rag_store.list_documents()
        return [
            {"id": d.id, "title": d.title, "chunk_count": d.chunk_count, "metadata": d.metadata}
            for d in docs
        ]

    @app.delete("/api/rag/documents/{doc_id}")
    async def delete_rag_document(doc_id: str):
        """删除 RAG 知识库中的指定文档。"""
        if _rag_store is None:
            raise HTTPException(503, "RAG 存储未初始化，请先发送一条聊天消息")
        _rag_store.delete_document(doc_id)
        return {"deleted": doc_id}

    @app.post("/api/rag/ingest")
    async def ingest_rag_document(req: RAGIngestRequest):
        """向 RAG 知识库入库文本。"""
        if _rag_store is None:
            await _get_agent()
        metadata = {"title": req.title} if req.title else None
        count = _rag_store.ingest_document(
            doc_id=req.doc_id, text=req.text, metadata=metadata,
        )
        return {"doc_id": req.doc_id, "chunk_count": count}

    @app.get("/api/agent/stats")
    async def agent_stats():
        """Agent 子系统统计：记忆、Skill、轨迹。"""
        agent = await _get_agent()
        return {
            "memory": agent.memory.get_stats(),
            "skills": {"count": len(agent.skills.list_skills())},
            "model": agent.model,
            "max_steps": agent.max_steps,
        }

    @app.post("/api/edit")
    async def edit_text(req: EditRequest):
        """Basic streaming edit endpoint used by the editor UI."""
        text = req.text or ""
        instruction = (req.instruction or "").strip()
        task_type = (req.task_type or "").lower()

        if task_type == "coherence" and req.previous:
            result = f"{req.previous.rstrip()}\n\n{text.strip()}".strip()
        elif task_type in {"polish", "expand"}:
            result = text.strip()
        else:
            result = text.strip() or instruction

        async def _stream() -> AsyncGenerator[dict, None]:
            yield {
                "event": "delta",
                "data": json.dumps({"content": result}, ensure_ascii=False),
            }

        return EventSourceResponse(_stream(), media_type="text/event-stream")

    @app.post("/api/complete")
    async def complete_text(req: CompletionRequest):
        """Inline completion endpoint. Returns empty text when no model is configured."""
        return {"completion": "", "usage": {"prompt_tokens": len(req.context), "completion_tokens": 0}}

    @app.get("/api/export/templates")
    async def export_templates():
        from pandoc_templates import get_templates, tectonic_available

        return {
            "templates": get_templates(),
            "tectonic_available": tectonic_available(),
        }

    @app.post("/api/export")
    async def export_latex(req: MarkdownExportRequest):
        from pandoc_templates import convert_markdown

        result = convert_markdown(
            req.markdown,
            template_id=req.template_id,
            output_format="tex",
            metadata={"title": req.title or ""},
        )
        if not result.get("success"):
            raise HTTPException(400, result.get("error") or "Export failed")
        return result

    @app.post("/api/export/pdf")
    async def export_pdf(req: MarkdownExportRequest):
        from pandoc_templates import convert_markdown

        result = convert_markdown(
            req.markdown,
            template_id=req.template_id,
            output_format="pdf",
            metadata={"title": req.title or ""},
        )
        if not result.get("success") or not result.get("pdf_path"):
            raise HTTPException(400, result.get("error") or "PDF export failed")
        pdf_path = Path(result["pdf_path"])
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"{req.title or 'paper'}.pdf")

    @app.get("/api/tectonic/status")
    async def tectonic_status():
        from pandoc_templates import tectonic_available, tectonic_version

        return {"available": tectonic_available(), "version": tectonic_version()}

    @app.post("/api/tectonic/install")
    async def tectonic_install():
        from pandoc_templates import install_tectonic

        result = install_tectonic()
        if not result.get("success"):
            raise HTTPException(400, result.get("error") or "Tectonic install failed")
        return result

    @app.get("/api/paper-assets/templates")
    async def paper_asset_templates():
        from paper_assets import get_template_list

        icon_map = {
            "generic": "Doc",
            "generic_article": "Doc",
            "ieee": "IEEE",
            "ieee_conference": "IEEE",
            "ieee_journal": "IEEE",
            "neurips": "N",
            "acm": "ACM",
            "lncs": "LNCS",
        }
        templates = [
            {**item, "icon": icon_map.get(item.get("id", ""), "Doc")}
            for item in get_template_list()
        ]
        return {"templates": templates}

    @app.post("/api/paper-assets/ingest")
    async def paper_assets_ingest():
        from paper_assets import ingest_paper_assets

        agent = await _get_agent()
        return ingest_paper_assets(agent.rag)

    @app.post("/api/paper-scaffold")
    async def paper_scaffold(req: PaperScaffoldRequest):
        from paper_assets import generate_scaffold

        return {
            "template_id": req.template_id,
            "markdown": generate_scaffold(req.template_id, req.title, req.sections),
        }

    @app.post("/api/paper-style-transfer")
    async def paper_style_transfer(req: PaperStyleTransferRequest):
        from paper_assets import get_style_examples

        return {
            "template_id": req.template_id,
            "section": req.section,
            "style_context": get_style_examples(req.template_id, req.section),
            "text": req.text,
        }

    argument_tasks: dict[str, dict] = {}

    def _argument_store():
        from src.argument import ArgumentStore

        return ArgumentStore(RUNTIME_DIR / "data" / "argument_tree.json")

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
    async def argument_create_tree(req: ArgumentTreeCreateRequest):
        return _argument_store().create_tree(req.topic, req.domain_tags, req.position)

    @app.get("/api/argument/tree")
    async def argument_get_tree():
        return _argument_tree_or_404()

    @app.put("/api/argument/node")
    async def argument_upsert_node(req: ArgumentNodeRequest):
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
    async def argument_get_node(node_id: str):
        tree = _argument_tree_or_404()
        return _argument_node_or_404(tree, node_id)

    @app.delete("/api/argument/node/{node_id}")
    async def argument_delete_node(node_id: str, cascade: bool = False):
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
    async def argument_expand(req: ArgumentExpandRequest):
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
                position={"x": base_x + (index - 1.5) * 180, "y": base_y},
            )
            children.append({
                "id": node["id"],
                "topic": node["topic"],
                "domain_tags": node["domain_tags"],
                "depth": node["depth"],
                "position": node["position"],
            })
        parent["status"] = "expanded"
        parent["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        store.save(tree)
        return {"parent_id": parent["id"], "children": children, "expanded_node": parent}

    @app.post("/api/argument/observe")
    async def argument_observe(req: ArgumentObserveRequest):
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, req.node_id)
        query = req.content_hint or node.get("content") or node.get("topic", "")
        recommendations = []
        if _rag_store is not None and query.strip():
            for item in _rag_store.retrieve_context(query, top_k=5):
                score = max(0.0, 1.0 - float(item.get("distance", 1.0)))
                if score < 0.85:
                    continue
                meta = item.get("metadata") or {}
                recommendations.append({
                    "doc_id": meta.get("doc_id") or item.get("id"),
                    "citation_key": meta.get("citation_key") or meta.get("title") or meta.get("doc_id") or item.get("id"),
                    "title": meta.get("title") or meta.get("doc_id") or item.get("id"),
                    "authors": meta.get("authors", []),
                    "year": meta.get("year"),
                    "relevance_score": round(score, 3),
                    "excerpt": item.get("text", "")[:240],
                    "match_type": "keyword",
                })
        return {"node_id": node["id"], "recommendations": recommendations}

    @app.post("/api/argument/bind")
    async def argument_bind(req: ArgumentBindRequest):
        store = _argument_store()
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, req.node_id)
        ref = {
            "doc_id": req.doc_id,
            "citation_key": req.doc_id,
            "relevance_score": req.relevance_score,
            "binding_type": req.binding_type,
            "bound_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return {"node_id": node["id"], "reference": store.bind_reference(tree, node["id"], ref)}

    @app.get("/api/argument/recommendations/{node_id}")
    async def argument_recommendations(node_id: str):
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, node_id)
        return {"node_id": node["id"], "references": node.get("references", [])}

    @app.delete("/api/argument/bind/{node_id}/{doc_id}")
    async def argument_unbind(node_id: str, doc_id: str):
        store = _argument_store()
        tree = _argument_tree_or_404()
        node = _argument_node_or_404(tree, node_id)
        store.unbind_reference(tree, node["id"], doc_id)
        return {"node_id": node["id"], "doc_id": doc_id, "message": "Reference unbound successfully"}

    @app.post("/api/argument/review")
    async def argument_review(req: ArgumentReviewRequest):
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
    async def argument_flatten(req: ArgumentFlattenRequest):
        tree = _argument_tree_or_404()
        _argument_node_or_404(tree, req.node_id)
        task_id = f"flatten_task_{uuid.uuid4().hex[:8]}"
        out_dir = RUNTIME_DIR / "data" / "output"
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
    async def argument_flatten_stream(task_id: str):
        task = argument_tasks.get(task_id)
        if not task:
            raise HTTPException(404, "Task not found")

        async def _stream():
            yield {"event": "complete", "data": json.dumps(task, ensure_ascii=False)}

        return EventSourceResponse(_stream(), media_type="text/event-stream")

    @app.get("/api/argument/download/{task_id}")
    async def argument_download(task_id: str):
        task = argument_tasks.get(task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return FileResponse(task["output_path"], media_type="text/markdown", filename=f"{task_id}.md")

    @app.post("/api/compliance")
    async def compliance_check(req: ComplianceRequest):
        markdown = req.markdown or ""
        words = [w for w in markdown.replace("\n", " ").split(" ") if w.strip()]
        required = [
            s.strip().lower()
            for s in (req.required_sections or "").split(",")
            if s.strip()
        ]
        headings = set()
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip().lower().replace(" ", "_")
                headings.add(heading)
        missing = [s for s in required if s not in headings]
        return {
            "report": {
                "summary": {
                    "title": req.title,
                    "venue": req.venue,
                    "total_words": len(words),
                    "total_characters": len(markdown),
                    "missing_sections": len(missing),
                },
                "sections": {
                    "required": required,
                    "found": sorted(headings),
                    "missing": missing,
                },
                "recommendations": [
                    f"Add a {section.replace('_', ' ')} section." for section in missing
                ],
            }
        }

    @app.post("/api/export/word")
    async def export_word(req: WordExportRequest):
        """将 Markdown 文本导出为 .docx 文件（保留段落结构）。

        Args:
            req.content: Markdown 格式文本
            req.title: 文档标题（默认 "Scholar Assistant Export"）

        Returns:
            .docx 文件路径（30 分钟内有效）
        """
        from src.formatter.word_exporter import markdown_to_docx

        out_dir = output_dir if 'output_dir' in dir() else (RUNTIME_DIR / "data" / "output")
        out_dir.mkdir(parents=True, exist_ok=True)

        docx_path = out_dir / f"export_{uuid.uuid4().hex[:8]}.docx"
        markdown_to_docx(req.content, docx_path, title=req.title)

        return {
            "path": str(docx_path),
            "filename": docx_path.name,
            "size": docx_path.stat().st_size,
        }

    @app.get("/api/export/word/{filename}")
    async def download_word(filename: str):
        """下载导出的 .docx 文件。"""
        # 安全检查：只允许下载 data/output 目录下的 .docx 文件
        output_dir = RUNTIME_DIR / "data" / "output"
        safe_path = (output_dir / filename).resolve()
        if not str(safe_path).startswith(str(output_dir.resolve())):
            raise HTTPException(403, "禁止访问该文件")
        if not safe_path.exists() or safe_path.suffix.lower() != ".docx":
            raise HTTPException(404, "文件不存在")
        # 清理过期文件（超过 30 分钟）
        age_minutes = (time.time() - safe_path.stat().st_mtime) / 60
        if age_minutes > 30:
            safe_path.unlink(missing_ok=True)
            raise HTTPException(404, "文件已过期")

        return FileResponse(
            str(safe_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
        )

    @app.on_event("shutdown")
    async def _shutdown():
        if _agent_instance is not None:
            await _agent_instance.close()
            _agent_instance.memory.close()

    return app
