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

# Plugin 系统 (延迟导入，不影响核心翻译功能)
try:
    from src.plugin import PluginRegistry, register_builtin
    _PLUGIN_AVAILABLE = True
except ImportError:
    _PLUGIN_AVAILABLE = False
    PluginRegistry = None
    register_builtin = None

# Argument Mapping 子系统 (延迟导入)
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
    title: str = "研墨导出"


class CitationIndexRequest(BaseModel):
    content: str                    # Markdown 文本
    bibliography: list[dict] = []  # BibTeX 文献库
    style: str = "ieee"            # 引用格式: ieee/apa/gbt7714


class VisionAnalysisRequest(BaseModel):
    analysis_type: str = "general"  # general/chart/table/formula


class ZoteroSearchRequest(BaseModel):
    query: str                         # 搜索关键词
    item_type: str | None = None     # 限定文献类型
    limit: int = 20                  # 最大返回数量


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

    _app_title = "研墨 API (cloud-only)" if cloud_only else "研墨 API"
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
        "http://127.0.0.1:5173",
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

    # ── Plugin 系统初始化 ───────────────────────────────────────
    if _PLUGIN_AVAILABLE:
        plugin_registry = PluginRegistry()
        register_builtin(plugin_registry)
        route_count = plugin_registry.attach_to_app(app)
        logger.info("Plugin 系统初始化完成: %d 条路由注册", route_count)
    else:
        plugin_registry = None
        logger.warning("Plugin 系统不可用")

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
        reachable, error_detail = client.health_check_detail()
        return {"reachable": reachable, "error": error_detail}

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
            "filename": file.filename or "unknown",
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

            # 自动将翻译结果入库到 RAG 知识库
            if _rag_store is not None:
                try:
                    src_lang = config.get("translator", {}).get("source_lang", "en")
                    src_label = "英文" if src_lang == "en" else src_lang
                    rag_meta = {
                        "title": f"[翻译] {task['filename']}",
                        "source": "translation",
                        "source_lang": src_label,
                    }
                    # 入库原文 + 译文对照，便于后续问答
                    dual_text = f"[原文]\n{clean_result.text}\n\n[译文]\n{content}"
                    _rag_store.ingest_document(
                        doc_id=f"trans_{task_id}",
                        text=dual_text,
                        metadata=rag_meta,
                    )
                    logger.info("翻译结果已自动入库 RAG: trans_%s", task_id)
                except Exception as rag_err:
                    logger.warning("翻译结果入库 RAG 失败（不影响翻译）: %s", rag_err)

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

    @app.get("/api/plugins")
    def get_plugins():
        """返回已注册的插件和工具列表。"""
        if not _PLUGIN_AVAILABLE or plugin_registry is None:
            return {"available": False, "servers": [], "tools": []}
        return {
            "available": True,
            **plugin_registry.get_stats(),
            "tools": plugin_registry.get_all_tools(),
        }

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

            # 可选: 初始化时分复用调度器（仅 Ollama 模式，云端不需要）
            scheduler = None
            vram_cfg = agent_cfg.get("vram", {})
            _use_cloud_engine = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            if vram_cfg.get("enabled", True) and not _use_cloud_engine:
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
                api_format=PROVIDER_PRESETS.get(cloud_cfg.get("provider", "openai"), {}).get("api_format", "openai") if use_cloud else "openai",
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

    @app.post("/api/rag/upload")
    async def upload_rag_document(file: UploadFile = File(...)):
        """上传文件并直接入库到 RAG 知识库（不经翻译管道）。"""
        if _rag_store is None:
            await _get_agent()

        if not file.filename:
            raise HTTPException(400, "文件名不能为空")

        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
            raise HTTPException(400, f"不支持的文件格式: {ext}。支持: {supported}")

        doc_id = f"upload_{uuid.uuid4().hex[:8]}"

        # 保存到临时目录
        upload_dir = Path("data/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        temp_path = upload_dir / f"{doc_id}_{file.filename}"

        try:
            total = 0
            with open(temp_path, "wb") as f:
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_SIZE:
                        f.close()
                        temp_path.unlink(missing_ok=True)
                        raise HTTPException(413, "文件过大，最大支持 200 MB")
                    f.write(chunk)

            # 解析文档
            doc = await asyncio.to_thread(extract_document, str(temp_path))
            raw_text = doc.full_text

            if not raw_text.strip():
                raise HTTPException(400, "文档内容为空")

            # 入库 RAG
            metadata = {
                "title": file.filename,
                "source": "user_upload",
                "page_count": doc.page_count,
            }
            chunk_count = _rag_store.ingest_document(
                doc_id=doc_id,
                text=raw_text,
                metadata=metadata,
            )

            return {
                "doc_id": doc_id,
                "title": file.filename,
                "chunk_count": chunk_count,
                "chars": len(raw_text),
            }

        finally:
            temp_path.unlink(missing_ok=True)

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
        """AI-powered streaming edit endpoint used by the editor UI.

        Routes the instruction + text through the configured AI backend
        (cloud API when engine=cloud, otherwise Ollama) and streams the
        result back as SSE events.
        """
        text = req.text or ""
        instruction = (req.instruction or "").strip()
        task_type = (req.task_type or "").lower()

        if not instruction:
            return EventSourceResponse(
                _edit_echo(text), media_type="text/event-stream"
            )

        config = _load_config()
        trans_cfg = config.get("translator", {})
        engine = trans_cfg.get("engine", "ollama")

        # Build messages for the LLM
        if text.strip():
            system_prompt = (
                "你是一个学术写作助手。用户会提供一段文本和一条指令，"
                "请严格根据指令处理文本。直接输出处理后的结果，不要添加解释或前言。"
                "如果指令不是对文本进行编辑操作（如问候、闲聊、提问），请正常回复。"
            )
            user_msg = f"--- 文本 ---\n{text}\n--- 指令 ---\n{instruction}"
        else:
            system_prompt = (
                "你是一个学术研究助手，可以帮助用户进行学术写作、翻译、润色、"
                "文献检索、论文大纲等任务。请用中文回复用户的问题。"
            )
            user_msg = instruction

        if engine == "cloud":
            cloud_cfg = trans_cfg.get("cloud", {})
            base_url = cloud_cfg.get("base_url", "").rstrip("/")
            api_key = (cloud_cfg.get("api_key") or "").strip()
            model = cloud_cfg.get("model", "gpt-4o")
            if not base_url or not api_key:
                return EventSourceResponse(
                    _edit_error("云端 API 未配置，请在设置中填写 API Key"),
                    media_type="text/event-stream",
                )
            return EventSourceResponse(
                _edit_stream_cloud(base_url, api_key, model, system_prompt, user_msg),
                media_type="text/event-stream",
            )
        else:
            ollama_url = trans_cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
            model = trans_cfg.get("model", "qwen3:8b")
            return EventSourceResponse(
                _edit_stream_ollama(ollama_url, model, system_prompt, user_msg),
                media_type="text/event-stream",
            )

    async def _edit_echo(text: str) -> AsyncGenerator[dict, None]:
        yield {"event": "delta", "data": json.dumps({"content": text.strip()}, ensure_ascii=False)}

    async def _edit_error(msg: str) -> AsyncGenerator[dict, None]:
        yield {"event": "delta", "data": json.dumps({"content": msg}, ensure_ascii=False)}

    async def _edit_stream_cloud(
        base_url: str, api_key: str, model: str,
        system_prompt: str, user_msg: str,
    ) -> AsyncGenerator[dict, None]:
        import httpx
        full_content = ""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 8192,
                        "stream": True,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            full_content += token
        except Exception as e:
            logger.error("Edit cloud stream error: %s", e)
            if not full_content:
                full_content = f"AI 处理失败: {e}"

        yield {"event": "delta", "data": json.dumps({"content": full_content}, ensure_ascii=False)}

    async def _edit_stream_ollama(
        ollama_url: str, model: str,
        system_prompt: str, user_msg: str,
    ) -> AsyncGenerator[dict, None]:
        import httpx
        full_content = ""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{ollama_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        "stream": True,
                        "options": {"temperature": 0.3, "num_predict": 8192},
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_content += token
                        if chunk.get("done"):
                            break
        except Exception as e:
            logger.error("Edit Ollama stream error: %s", e)
            if not full_content:
                full_content = f"AI 处理失败（Ollama 未启动？）: {e}"

        yield {"event": "delta", "data": json.dumps({"content": full_content}, ensure_ascii=False)}

    @app.post("/api/complete")
    async def complete_text(req: CompletionRequest):
        """Inline completion endpoint powered by the configured AI backend."""
        context = (req.context or "").strip()
        if not context:
            return {"completion": "", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

        config = _load_config()
        trans_cfg = config.get("translator", {})
        engine = trans_cfg.get("engine", "ollama")

        prompt = (
            "You are an academic writing auto-complete assistant. "
            "Continue the text naturally. Output ONLY the continuation, "
            "no explanations, no markdown, no preamble.\n\n"
            f"Context:\n{context[-2000:]}"
        )

        try:
            if engine == "cloud":
                cloud_cfg = trans_cfg.get("cloud", {})
                base_url = cloud_cfg.get("base_url", "").rstrip("/")
                api_key = (cloud_cfg.get("api_key") or "").strip()
                model = cloud_cfg.get("model", "gpt-4o")
                if not base_url or not api_key:
                    return {"completion": "", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
                import httpx
                async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.2,
                            "max_tokens": req.max_tokens,
                            "stream": False,
                        },
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
            else:
                ollama_url = trans_cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
                model = trans_cfg.get("model", "qwen3:8b")
                import httpx
                async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                    resp = await client.post(
                        f"{ollama_url}/api/chat",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False,
                            "options": {"temperature": 0.2, "num_predict": req.max_tokens},
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    text = data.get("message", {}).get("content", "")
                    usage = {"prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)}

            # Strip think tags and code blocks
            import re
            text = re.sub(r"<think.*?>.*?</think.*?>", "", text, flags=re.DOTALL).strip()
            text = text.lstrip("```").rstrip("```").strip()

            return {"completion": text, "usage": usage}
        except Exception as e:
            logger.debug("Inline completion failed: %s", e)
            return {"completion": "", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

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
            req.title: 文档标题（默认 "研墨导出"）

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

    # ── 图片上传 ────────────────────────────────────────────────
    @app.post("/api/upload/image")
    async def upload_image(file: UploadFile = File(...)):
        """上传图片到 assets 目录

        Returns:
            {"path": "...", "filename": "...", "url": "..."}
        """
        # 检查文件类型
        allowed_types = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
        if file.content_type not in allowed_types:
            raise HTTPException(400, f"不支持的图片格式: {file.content_type}")

        # 创建 assets 目录
        assets_dir = data_root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一文件名
        ext = Path(file.filename).suffix.lower() if file.filename else ".png"
        filename = f"{uuid.uuid4().hex[:12]}{ext}"
        file_path = assets_dir / filename

        # 保存文件
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:  # 50MB 上限
            raise HTTPException(413, "图片大小超过 50MB 限制")
        with open(file_path, "wb") as f:
            f.write(content)

        # 返回相对路径（前端可拼装为完整 URL）
        relative_path = f"/api/assets/{filename}"
        return {
            "path": str(file_path),
            "filename": filename,
            "url": relative_path,
            "size": len(content),
        }

    @app.get("/api/assets/{filename}")
    async def serve_asset(filename: str):
        """提供 assets 目录下的静态文件访问"""
        assets_dir = data_root / "assets"
        safe_path = (assets_dir / filename).resolve()

        # 安全检查
        if not str(safe_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(403, "禁止访问该文件")
        if not safe_path.exists():
            raise HTTPException(404, "文件不存在")

        # 根据扩展名返回正确的 Content-Type
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        ext = safe_path.suffix.lower()
        media_type = content_types.get(ext, "application/octet-stream")

        return FileResponse(str(safe_path), media_type=media_type)

    # ── MCP Vision 图像分析 ───────────────────────────────────
    @app.post("/api/vision/analyze")
    async def analyze_image(
        file: UploadFile = File(...),
        analysis_type: str = "general",
    ):
        """MCP 多模态图像分析（OCR、图表理解、表格识别）

        Args:
            file: 图片文件
            analysis_type: 分析类型
                - general: 通用描述 + 文字识别
                - chart: 图表分析（柱状图、折线图等）
                - table: 表格提取
                - formula: 公式识别

        Returns:
            {
                "text": "识别的文字/描述",
                "chart_type": "bar/line/pie/table/...",
                "chart_description": "图表详细描述",
                "table_data": [["col1", "col2"], ...],
                "key_findings": ["要点1", ...],
                "raw_description": "原始API返回"
            }
        """
        # 保存上传的图片
        assets_dir = data_root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(file.filename).suffix.lower() if file.filename else ".png"
        temp_filename = f"vision_{uuid.uuid4().hex[:12]}{ext}"
        temp_path = assets_dir / temp_filename

        content = await file.read()
        if len(content) > 20 * 1024 * 1024:  # 20MB 上限
            raise HTTPException(413, "图片大小超过 20MB 限制")
        with open(temp_path, "wb") as f:
            f.write(content)

        try:
            # 调用 Vision Client
            from src.mcp.vision_client import VisionClient

            client = VisionClient()
            result = await client.analyze_image(temp_path, analysis_type=analysis_type)

            return result.to_dict()
        finally:
            # 清理临时文件
            try:
                temp_path.unlink(missing_ok=True)
            except PermissionError:
                logger.warning("Vision temporary file is still locked, skip cleanup: %s", temp_path)

    @app.post("/api/vision/ocr")
    async def ocr_image(file: UploadFile = File(...)):
        """OCR 专用接口 — 识别图片中的文字

        Returns:
            {"text": "识别的文字内容", ...}
        """
        return await analyze_image(file, analysis_type="general")

    @app.post("/api/vision/chart")
    async def analyze_chart(file: UploadFile = File(...)):
        """图表分析接口

        Returns:
            {"chart_type": "...", "chart_description": "...", "key_findings": [...], ...}
        """
        return await analyze_image(file, analysis_type="chart")

    @app.post("/api/vision/table")
    async def extract_table(file: UploadFile = File(...)):
        """表格提取接口

        Returns:
            {"table_data": [["col1", "col2"], ...], ...}
        """
        return await analyze_image(file, analysis_type="table")

    # ── 文献引用索引 ──────────────────────────────────────────
    @app.put("/api/citation/index")
    async def index_citations(req: CitationIndexRequest):
        """文献引用索引处理

        将 Markdown 中的 [@key] 替换为 [编号]，并生成参考文献节。

        Args:
            req.content: Markdown 文本
            req.bibliography: BibTeX 文献库
            req.style: 引用格式 (ieee/apa/gbt7714)

        Returns:
            {
                "text": "替换引用后的文本",
                "citations": [{"key": "...", "number": 1, "found": true}, ...],
                "index": {"key1": 1, "key2": 2, ...},
                "bibliography": "参考文献\n[1] ..."
            }
        """
        from src.citation.indexer import CitationIndexer

        indexer = CitationIndexer()
        result = indexer.process(
            text=req.content,
            bibliography=req.bibliography,
            style=req.style,
            include_reference_section=True,
        )

        return result

    @app.get("/api/citation/extract")
    async def extract_citations(content: str):
        """提取文本中的文献引用（不处理）

        用于前端预览有多少引用需要处理。
        """
        from src.citation.indexer import CitationIndexer

        indexer = CitationIndexer()
        keys = indexer.extract_citations(content)
        index = indexer.build_index(content)

        return {
            "keys": keys,
            "unique_count": len(index),
            "index": index,
        }

    # ── Zotero 文献管理 ──────────────────────────────────────────
    @app.get("/api/zotero/status")
    async def zotero_status():
        """检查 Zotero API 连接状态"""
        try:
            from src.zotero.client import ZoteroClient
            client = ZoteroClient()
            if not client.api_key or not client.user_id:
                return {
                    "connected": False,
                    "message": "未配置 Zotero API Key 或 User ID",
                }
            return {
                "connected": True,
                "user_id": client.user_id,
                "style": client.style,
            }
        except Exception as e:
            return {
                "connected": False,
                "message": str(e),
            }

    @app.post("/api/zotero/search")
    async def search_zotero(req: ZoteroSearchRequest):
        """搜索 Zotero 文献库

        Args:
            req.query: 搜索关键词
            req.item_type: 限定文献类型（可选）
            req.limit: 最大返回数量（默认20）

        Returns:
            文献列表，每个文献包含详情和引用 key
        """
        try:
            from src.zotero.client import ZoteroClient

            client = ZoteroClient()
            items = client.search(
                query=req.query,
                item_type=req.item_type,
                limit=req.limit,
            )

            return {
                "count": len(items),
                "items": [item.to_dict() for item in items],
            }
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            logger.error("Zotero 搜索失败: %s", e)
            raise HTTPException(500, f"Zotero 搜索失败: {e}")

    @app.get("/api/zotero/item/{item_key}")
    async def get_zotero_item(item_key: str):
        """获取单条 Zotero 文献详情

        Args:
            item_key: 文献 key

        Returns:
            文献详情，包含 BibTeX 格式
        """
        try:
            from src.zotero.client import ZoteroClient

            client = ZoteroClient()
            item = client.get_item(item_key)

            if not item:
                raise HTTPException(404, f"文献不存在: {item_key}")

            return item.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("获取 Zotero 文献失败: %s", e)
            raise HTTPException(500, f"获取文献失败: {e}")

    @app.get("/api/zotero/item/{item_key}/bibtex")
    async def get_zotero_item_bibtex(item_key: str):
        """导出单条文献为 BibTeX 格式"""
        try:
            from src.zotero.client import ZoteroClient

            client = ZoteroClient()
            item = client.get_item(item_key)

            if not item:
                raise HTTPException(404, f"文献不存在: {item_key}")

            return {
                "key": item_key,
                "bibtex": item.to_bibtex(),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("导出 BibTeX 失败: %s", e)
            raise HTTPException(500, f"导出失败: {e}")

    @app.post("/api/zotero/export")
    async def export_zotero_bibtex(item_keys: list[str] | None = None):
        """批量导出 BibTeX

        Args:
            item_keys: 要导出的文献 key 列表，None 则导出全部

        Returns:
            BibTeX 格式文本
        """
        try:
            from src.zotero.client import ZoteroClient

            client = ZoteroClient()
            bibtex = client.export_bibtex(item_keys)

            return {
                "bibtex": bibtex,
                "count": len(bibtex.split("\n\n")) if bibtex else 0,
            }
        except Exception as e:
            logger.error("导出 BibTeX 失败: %s", e)
            raise HTTPException(500, f"导出失败: {e}")

    @app.post("/api/zotero/citations")
    async def get_zotero_citations(item_keys: list[str]):
        """获取多条文献的引用信息

        Args:
            item_keys: 文献 key 列表

        Returns:
            文献列表，包含 Markdown 引用格式
        """
        try:
            from src.zotero.client import ZoteroClient

            client = ZoteroClient()
            items = client.get_items_by_keys(item_keys)

            return {
                "count": len(items),
                "items": [item.to_dict() for item in items],
                "citations": [item.to_markdown_citation() for item in items],
            }
        except Exception as e:
            logger.error("获取引用失败: %s", e)
            raise HTTPException(500, f"获取引用失败: {e}")

    # ── Argument Mapping 端点 ──────────────────────────────────────────

    if _ARGUMENT_AVAILABLE:
        _argument_store = ArgumentStore(persist_dir=str(data_root))
        _logic_checker = LogicChecker()
        _argument_expander = ArgumentExpander(_argument_store)
        _argument_observer = ArgumentObserver(_argument_store)
        _feedback_generator = FeedbackGenerator()
        _argument_flattener = ArgumentFlattener()
        _flatten_tasks: dict[str, dict] = {}

        def _cleanup_flatten_tasks() -> None:
            done_ids = [tid for tid, t in _flatten_tasks.items() if t["status"] in ("done", "error")]
            if len(done_ids) <= MAX_TASKS:
                return
            for tid in done_ids[:len(done_ids) - MAX_TASKS]:
                del _flatten_tasks[tid]

        def _get_cloud_client_for_argument():
            """获取 Argument 模块使用的 CloudClient。"""
            config = _load_config()
            trans_cfg = config.get("translator", {})
            cloud_cfg = trans_cfg.get("cloud", {})
            if not cloud_cfg.get("api_key"):
                return None
            return _build_cloud_client(trans_cfg, cloud_cfg)

        def _ensure_rag_store() -> Any:
            """确保 RAG Store 已初始化（复用 Agent 懒加载逻辑）。"""
            nonlocal _rag_store
            if _rag_store is not None:
                return _rag_store
            if _AGENT_AVAILABLE:
                config = _load_config()
                agent_cfg = config.get("agent", {})
                rag_cfg = agent_cfg.get("rag", {})
                rag_dir = RUNTIME_DIR / rag_cfg.get("persist_dir", "data/chromadb")
                _rag_store = RAGStore(
                    persist_dir=str(rag_dir),
                    collection_name=rag_cfg.get("collection_name", "scholar_docs"),
                    chunk_size=rag_cfg.get("chunk_size", 512),
                    chunk_overlap=rag_cfg.get("chunk_overlap", 64),
                )
            return _rag_store

        class _ArgumentError(HTTPException):
            """Argument 端点统一错误：响应体包含 detail + error_code + timestamp。"""
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
        def argument_get_tree():
            tree = _argument_store.get_tree()
            if tree.root_id is None:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")
            return tree.model_dump()

        @app.post("/api/argument/tree", status_code=201)
        def argument_create_tree(req: CreateTreeRequest):
            root = _argument_store.create_tree(
                topic=req.topic,
                domain_tags=req.domain_tags,
                position=req.position,
            )
            return _argument_store.get_tree().model_dump()

        @app.put("/api/argument/node")
        def argument_upsert_node(req: UpsertNodeRequest):
            if req.id and req.parent_id:
                parent = _argument_store.get_node(req.parent_id)
                if not parent:
                    _arg_error(400, "Invalid parent_id", "INVALID_PARENT")

            is_update = req.id is not None and req.id in _argument_store.get_tree().nodes
            node = _argument_store.upsert_node(
                **{k: v for k, v in req.model_dump().items() if v is not None},
            )
            return JSONResponse(content=node.model_dump(), status_code=200 if is_update else 201)

        @app.delete("/api/argument/node/{node_id}")
        def argument_delete_node(node_id: str, cascade: bool = False):
            deleted = _argument_store.delete_node(node_id, cascade=cascade)
            if not deleted:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return {"deleted": deleted, "message": f"Deleted {len(deleted)} nodes"}

        @app.get("/api/argument/node/{node_id}")
        def argument_get_node(node_id: str):
            node = _argument_store.get_node(node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return node.model_dump()

        @app.post("/api/argument/expand")
        async def argument_expand(req: ExpandRequest):
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
        def argument_observe(req: ObserveRequest):
            return _argument_observer.observe(
                node_id=req.node_id,
                content_hint=req.content_hint,
                rag_store=_ensure_rag_store(),
            )

        @app.post("/api/argument/bind")
        def argument_bind(req: BindRequest):
            node = _argument_store.get_node(req.node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")

            citation_key = req.doc_id
            rag = _ensure_rag_store()
            if rag is not None:
                for doc in rag.list_documents():
                    if doc.id == req.doc_id:
                        citation_key = doc.title or req.doc_id
                        break

            updated = _argument_store.bind_reference(
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

        @app.delete("/api/argument/bind/{node_id}/{doc_id}")
        def argument_unbind(node_id: str, doc_id: str):
            ok = _argument_store.unbind_reference(node_id, doc_id)
            if not ok:
                _arg_error(404, "Node or reference not found", "NODE_NOT_FOUND")
            return {"node_id": node_id, "doc_id": doc_id, "message": "Reference unbound successfully"}

        @app.post("/api/argument/review")
        async def argument_review(req: ReviewRequest):
            tree = _argument_store.get_tree()
            if not tree.root_id:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")

            target_id = req.node_id if req.node_id != "root" else tree.root_id
            if target_id not in tree.nodes:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            subtree_ids = _argument_store.get_subtree_ids(target_id) if req.include_subtree else [target_id]

            issues = _logic_checker.check(tree, subtree_ids)

            cloud_client = _get_cloud_client_for_argument()
            node_feedbacks = await _feedback_generator.generate(
                tree, issues, cloud_client=cloud_client,
            )

            # Update nodes with feedback
            for nid, fb in node_feedbacks.items():
                _argument_store.update_node_fields(
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
        def argument_flatten(req: FlattenRequest):
            tree = _argument_store.get_tree()
            if not tree.root_id:
                _arg_error(404, "Argument tree not found", "TREE_NOT_FOUND")

            import uuid as _uuid
            task_id = f"flatten_{_uuid.uuid4().hex[:8]}"
            _flatten_tasks[task_id] = {
                "status": "processing",
                "request": req.model_dump(),
                "tree_snapshot": tree.model_dump(),
            }
            return {"task_id": task_id, "status": "processing"}

        @app.get("/api/argument/flatten/{task_id}/stream")
        async def argument_flatten_stream(task_id: str):
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

        @app.get("/api/argument/download/{task_id}")
        def argument_download(task_id: str):
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
            node = _argument_store.get_node(node_id)
            if not node:
                _arg_error(404, "Node not found", "NODE_NOT_FOUND")
            return {
                "node_id": node_id,
                "references": [r.model_dump() for r in node.references],
            }

    @app.on_event("shutdown")
    async def _shutdown():
        if _agent_instance is not None:
            await _agent_instance.close()
            _agent_instance.memory.close()

    return app
