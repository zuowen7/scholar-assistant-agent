"""FastAPI 应用工厂 — 本地(Ollama+云) 与 纯云端 两种模式"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import AsyncGenerator, Literal

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

# 学术写作 Prompt 引擎（延迟导入，prompts 目录可选）
try:
    from prompts.loader import (
        get_system_prompt,
        render_polish_prompt,
        render_expand_prompt,
        render_coherence_prompt,
        render_ghost_text_prompt,
        parse_llm_output,
    )
    _PROMPTS_AVAILABLE = True
except ImportError:
    _PROMPTS_AVAILABLE = False

# Agent 子系统 (延迟导入，chromadb 未安装时不影响翻译功能)
try:
    from src.agent.agent import AgentLoop
    from src.agent.models import Message
    from src.agent.rag import RAGStore
    from src.agent.tools import create_default_registry
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
    network: dict | None = None


def get_proxy() -> str:
    """获取代理地址: 优先读配置文件 network.proxy，其次读环境变量。"""
    config = _load_config()
    proxy = config.get("network", {}).get("proxy", "")
    if proxy:
        return proxy
    # 兜底: 环境变量
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("http_proxy")
        or os.environ.get("all_proxy")
        or ""
    )


class FilePathPayload(BaseModel):
    path: str


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None
    context: str = ""  # 当前文档内容，作为 Agent 的上下文


class RAGIngestRequest(BaseModel):
    doc_id: str
    text: str
    title: str = ""


class EditRequest(BaseModel):
    text: str
    instruction: str = "润色这段学术文本，使其更加地道和专业"
    task_type: Literal["polish", "coherence", "expand", "grammar"] = "polish"
    previous: str = ""  # 前一段落（coherence 模式需要）


class CompleteRequest(BaseModel):
    context: str           # 当前光标前的文本（最后 N 行）
    after: str = ""        # 光标后的文本（可选，用于上下文）
    max_tokens: int = 128  # 补全长度限制


class ExportRequest(BaseModel):
    markdown: str
    template_id: str = "generic"
    output_format: Literal["tex", "pdf"] = "tex"
    title: str = ""
    author: str = ""
    abstract: str = ""


class ComplianceRequest(BaseModel):
    markdown: str
    title: str = ""
    venue: str = ""
    required_sections: str = ""


class PaperScaffoldRequest(BaseModel):
    template_id: str = "generic"
    title: str = ""
    sections: list[str] = []


    class Config:
        # Allow "sections" to be optional empty list
        json_schema_extra = {"example": {"template_id": "neurips", "title": "My Paper", "sections": []}}


class StyleTransferRequest(BaseModel):
    text: str
    template_id: str = "neurips"
    section: str = "introduction"


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
    else:
        _config_cache = {}
    # 环境变量覆盖 API Key（优先于配置文件）
    env_key = os.environ.get("SCHOLAR_API_KEY", "").strip()
    if env_key:
        _config_cache.setdefault("translator", {}).setdefault("cloud", {})["api_key"] = env_key
    return copy.deepcopy(_config_cache)


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
        model=cloud_cfg.get("model", "glm-5.1"),
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

    title = "Scholar Translate API (Cloud)" if cloud_only else "Scholar Translate API"
    app = FastAPI(title=title, version="0.3.1")

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
        "http://127.0.0.1:5173",
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

    # ── 请求体大小限制中间件 ──
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        if request.method in ("POST", "PUT") and "content-length" in request.headers:
            try:
                content_length = int(request.headers["content-length"])
                if content_length > MAX_BODY_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"请求体过大，最大允许 {MAX_BODY_SIZE // 1024 // 1024} MB"},
                    )
            except (ValueError, KeyError):
                pass
        return await call_next(request)

    @app.get("/api/health")
    def health():
        payload = {"status": "ok", "version": "0.3.1"}
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
        if _busy_lock.locked():
            raise HTTPException(409, "已有翻译任务在运行，请等待完成")
        await _busy_lock.acquire()

        try:
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
        except HTTPException:
            _busy_lock.release()
            raise

    @app.post("/api/translate/path")
    async def start_translate_path(payload: FilePathPayload):
        if _busy_lock.locked():
            raise HTTPException(409, "已有翻译任务在运行，请等待完成")
        await _busy_lock.acquire()

        try:
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
        except HTTPException:
            _busy_lock.release()
            raise

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
            raise HTTPException(409, "任务锁已释放，请重新创建任务")
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
        if cfg.network:
            current["network"] = {**current.get("network", {}), **cfg.network}
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

    # ── AI 行内补全端点 ──────────────────────────────────────────────

    @app.post("/api/complete")
    async def ai_complete(req: CompleteRequest):
        r"""轻量 AI 补全端点，用于编辑器 Ghost Text（Alt+\ 触发）"""
        config = _load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        use_cloud = bool(cloud_cfg.get("api_key")) or cloud_only

        try:
            if use_cloud:
                key = (cloud_cfg.get("api_key") or "").strip()
                if not key:
                    return {"completion": ""}
                client: OllamaClient | CloudClient = _build_cloud_client(trans_cfg, cloud_cfg)
            else:
                ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get(
                    "ollama_base_url", "http://localhost:11434"
                )
                client = OllamaClient(
                    base_url=ollama_url,
                    model=trans_cfg.get("model", "qwen3:8b"),
                    temperature=0.2,
                    num_predict=req.max_tokens,
                    timeout=30.0,
                )

            # 使用 prompt 引擎生成 ghost text 专用提示
            if _PROMPTS_AVAILABLE:
                sys_p, user = render_ghost_text_prompt(
                    context=req.context[-2000:] if req.context else "",
                    after=req.after[:500] if req.after else "",
                )
                messages = [{"role": "user", "content": user}]
            else:
                # Fallback：简单续写提示
                ctx = (req.context or "")[-2000:]
                after = (req.after or "")[:500]
                sys_p = ""
                user = (
                    "Continue the academic paper text naturally.\n"
                    "Output ONLY the next sentence(s), no explanation, no markdown.\n\n"
                    f"Previous text:\n{ctx}\n\nContinue:"
                )
                messages = [{"role": "user", "content": user}]

            # 调用 chat()（绕过 translate 包装）
            result_text = await asyncio.wait_for(
                asyncio.to_thread(client.chat, messages, sys_p, req.max_tokens),
                timeout=15.0,
            )
            return {"completion": result_text.strip()}

        except Exception as e:
            logger.warning("AI complete failed: %s", e)
            return {"completion": ""}
        finally:
            if hasattr(client, "close"):
                client.close()

    # ── AI 文本编辑端点 ──────────────────────────────────────────────

    @app.post("/api/edit")
    async def start_edit(req: EditRequest):
        """SSE 流式 AI 文本编辑（润色/扩写/连贯性），不占用翻译锁"""
        config = _load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        use_cloud = bool(cloud_cfg.get("api_key")) or cloud_only

        async def _stream() -> AsyncGenerator[dict, None]:
            try:
                if use_cloud:
                    key = (cloud_cfg.get("api_key") or "").strip()
                    if not key:
                        raise ValueError("未配置云端 API Key")
                    client: OllamaClient | CloudClient = _build_cloud_client(trans_cfg, cloud_cfg)
                else:
                    ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get(
                        "ollama_base_url", "http://localhost:11434"
                    )
                    client = OllamaClient(
                        base_url=ollama_url,
                        model=trans_cfg.get("model", "qwen3:8b"),
                        temperature=trans_cfg.get("temperature", 0.3),
                        num_predict=trans_cfg.get("num_predict", 16384),
                        timeout=trans_cfg.get("timeout", 300.0),
                    )

                # 根据 task_type 选择 prompt 模板
                task = req.task_type or "polish"
                # 如果有 instruction 且不是标准 task_type，直接用 instruction 作为主 prompt
                chinese_task = req.instruction.strip()
                use_direct_instruction = bool(chinese_task) and task in ("polish", "expand", "coherence", "grammar")
                use_fallback_instruction = bool(chinese_task) and task not in ("polish", "expand", "coherence", "grammar")

                if use_direct_instruction:
                    # 直接使用用户中文指令，不套英文模板
                    sys_p = "你是一位专业的学术写作助手，负责帮助用户完善学术文本。请严格按照用户的要求处理文本，只输出处理结果，不要任何解释。"
                    user = f"{chinese_task}\n\n待处理文本：\n{req.text}"
                elif use_fallback_instruction:
                    # 非标准 task，直接用 instruction
                    sys_p = ""
                    user = f"{req.instruction}\n\n{req.text}"
                elif _PROMPTS_AVAILABLE:
                    if task == "polish":
                        sys_p, user = render_polish_prompt(text=req.text, language="en")
                    elif task == "expand":
                        sys_p, user = render_expand_prompt(draft=req.text, section_type="method")
                    elif task == "coherence":
                        sys_p, user = render_coherence_prompt(
                            current=req.text,
                            previous=req.previous,
                            section_goal="",
                        )
                    elif task == "grammar":
                        sys_p, user = render_polish_prompt(
                            text=req.text,
                            language="en",
                            field="General",
                            venue="academic paper",
                            terminology="",
                        )
                    else:
                        sys_p = ""
                        user = f"{req.instruction}\n\n{req.text}"
                else:
                    # Fallback：简单的指令式提示
                    sys_p = ""
                    user = f"指令：{req.instruction}\n\n待处理文本：\n{req.text}"

                messages = [{"role": "user", "content": user}]

                yield {
                    "event": "progress",
                    "data": json.dumps({"message": "AI 正在处理..."}),
                }

                result_text = await asyncio.wait_for(
                    asyncio.to_thread(client.chat, messages, sys_p, 2048),
                    timeout=60.0,
                )

                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "content": result_text.strip(),
                        "task": task,
                    }, ensure_ascii=False),
                }

            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": str(e)}),
                }
            finally:
                if hasattr(client, "close"):
                    client.close()

        return EventSourceResponse(
            _stream(),
            media_type="text/event-stream",
        )

    # ── Pandoc 导出端点 ──────────────────────────────────────────────

    from pandoc_templates import get_templates, convert_markdown, is_pandoc_available, pandoc_version
    from pandoc_templates import tectonic_available, tectonic_version, compile_pdf, install_tectonic

    @app.get("/api/export/templates")
    async def list_export_templates():
        """返回可用导出模板列表。"""
        return {
            "templates": get_templates(),
            "pandoc_available": is_pandoc_available(),
            "pandoc_version": pandoc_version(),
            "tectonic_available": tectonic_available(),
            "tectonic_version": tectonic_version(),
        }

    @app.get("/api/tectonic/status")
    async def tectonic_status():
        """检测 Tectonic LaTeX 引擎状态。"""
        return {
            "available": tectonic_available(),
            "version": tectonic_version(),
        }

    @app.post("/api/tectonic/install")
    async def tectonic_install():
        """自动下载安装 Tectonic LaTeX 引擎。"""
        if tectonic_available():
            return {"success": True, "error": "", "version": tectonic_version()}
        result = await asyncio.to_thread(install_tectonic)
        return result

    @app.post("/api/export/pdf")
    async def export_pdf(req: ExportRequest):
        """Markdown → LaTeX → PDF，返回 PDF 文件流。"""
        if not tectonic_available():
            raise HTTPException(400, "Tectonic 未安装。请在设置中安装 LaTeX 引擎。")

        # 1. Markdown → LaTeX
        meta = {}
        if req.title: meta["title"] = req.title
        if req.author: meta["author"] = req.author
        if req.abstract: meta["abstract"] = req.abstract

        tex_result = convert_markdown(
            markdown_text=req.markdown,
            template_id=req.template_id,
            output_format="tex",
            metadata=meta if meta else None,
        )
        if not tex_result["success"]:
            raise HTTPException(400, tex_result.get("error", "LaTeX 转换失败"))

        # 2. LaTeX → PDF
        pdf_result = compile_pdf(tex_result["tex"])
        if not pdf_result["success"]:
            raise HTTPException(500, pdf_result.get("error", "PDF 编译失败"))

        pdf_path = pdf_result["pdf_path"]
        filename = (req.title or "paper").replace(" ", "_") + ".pdf"
        return FileResponse(
            pdf_path,
            filename=filename,
            media_type="application/pdf",
        )

    @app.post("/api/export")
    async def export_markdown(req: ExportRequest):
        """
        将 Markdown 转换为 LaTeX（.tex）并返回源码。

        前端流程：
        1. 调用 /api/export/templates 获取可用模板
        2. 调用本接口，传入 markdown 和 template_id
        3. 返回 .tex 源码，前端弹出下载或复制到剪贴板
        """
        meta = {}
        if req.title:
            meta["title"] = req.title
        if req.author:
            meta["author"] = req.author
        if req.abstract:
            meta["abstract"] = req.abstract

        result = convert_markdown(
            markdown_text=req.markdown,
            template_id=req.template_id,
            output_format=req.output_format,
            metadata=meta if meta else None,
        )

        if not result["success"]:
            return JSONResponse(
                status_code=400,
                content={"error": result["error"], "tex": ""},
            )

        return {
            "tex": result["tex"],
            "template": result.get("template", req.template_id),
            "pandoc_version": result.get("pandoc_version", ""),
            "suggestion": (
                "建议将 .tex 文件拖入 Overleaf (overleaf.com) 或本地 TeX 编辑器编译。"
                if not is_pandoc_available()
                else ""
            ),
        }

    # ── AI 内容合规检查端点 ─────────────────────────────────────────

    @app.post("/api/compliance")
    async def check_compliance(req: ComplianceRequest):
        """
        AI 内容合规预检 — 分析 Markdown 论文，输出只读 JSON 报告。

        检查维度：字数/章节完整性/术语一致性/引用格式/幻觉风险/可读性
        不修改原文，只输出报告。
        """
        if not req.markdown.strip():
            return {"error": "文档内容为空", "report": None}

        # 优先使用云端 API
        config = _load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        use_cloud = bool(cloud_cfg.get("api_key")) or cloud_only

        try:
            if use_cloud:
                key = (cloud_cfg.get("api_key") or "").strip()
                if not key:
                    raise ValueError("未配置云端 API Key")
                client: OllamaClient | CloudClient = _build_cloud_client(trans_cfg, cloud_cfg)
            else:
                ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get(
                    "ollama_base_url", "http://localhost:11434"
                )
                client = OllamaClient(
                    base_url=ollama_url,
                    model=trans_cfg.get("model", "qwen3:8b"),
                    temperature=0.2,
                    num_predict=2048,
                    timeout=60.0,
                )

            # 渲染合规检查 prompt
            if _PROMPTS_AVAILABLE:
                from prompts.loader import render_compliance_prompt, parse_compliance_json
                sys_p, user = render_compliance_prompt(
                    text=req.markdown,
                    title=req.title,
                    venue=req.venue,
                    required_sections=req.required_sections,
                )
            else:
                sys_p = ""
                user = (
                    "Analyze the following academic paper and output a compliance report as JSON.\n"
                    f"Title: {req.title or 'Untitled'}\n"
                    f"Venue: {req.venue or 'general academic paper'}\n\n"
                    f"Paper content:\n{req.markdown[:6000]}\n\n"
                    "Output a JSON object with fields: summary (total_characters, total_words, compliance_score, overall_status), "
                    "structure (required_sections, issues), terminology (consistent_terms, inconsistent_terms, issues), "
                    "citation (format_issues, total_citations, issues), hallucination_risk (flags, risk_level, issues), "
                    "readability (avg_sentence_length, long_sentences, issues)."
                )

            messages = [{"role": "user", "content": user}]
            raw_response = await asyncio.wait_for(
                asyncio.to_thread(client.chat, messages, sys_p, 2048),
                timeout=60.0,
            )

            # 解析 JSON 响应
            if _PROMPTS_AVAILABLE:
                from prompts.loader import parse_compliance_json
                report = parse_compliance_json(raw_response)
            else:
                # 简单 JSON 解析
                try:
                    import json as _json
                    report = _json.loads(raw_response)
                except Exception:
                    report = {
                        "error": "JSON 解析失败",
                        "raw_preview": raw_response[:500],
                        "summary": {"compliance_score": 0, "overall_status": "fail"},
                    }

            return {"report": report, "error": "" if "error" not in report else ""}

        except Exception as e:
            logger.warning("Compliance check failed: %s", e)
            return {"report": None, "error": str(e)}
        finally:
            if hasattr(client, "close"):
                client.close()

    # ── Agent / RAG 端点 ──────────────────────────────────────────────

    _agent_instance: AgentLoop | None = None
    _rag_store: RAGStore | None = None
    _paper_rag: RAGStore | None = None
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
            _rag_store = RAGStore(
                persist_dir=str(rag_dir),
                collection_name=rag_cfg.get("collection_name", "scholar_docs"),
                chunk_size=rag_cfg.get("chunk_size", 512),
                chunk_overlap=rag_cfg.get("chunk_overlap", 64),
            )

            # 初始化工具注册表 — 注入翻译客户端和 LLM 调用函数
            # 构建 LLM 调用函数（供 polish_text / generate_outline / summarize_text 使用）
            _llm_call_fn = None
            use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"
            cloud_cfg_raw = trans_cfg.get("cloud", {})
            cloud_key = (cloud_cfg_raw.get("api_key") or "").strip()

            if use_cloud and cloud_key:
                # 云端 LLM 调用函数
                _tool_client = _build_cloud_client(trans_cfg, cloud_cfg_raw)
                def _llm_call_fn(prompt: str) -> str:
                    try:
                        _tool_client.system_prompt = "You are a helpful academic writing assistant. Follow the user's instructions precisely. Output ONLY the requested content, no explanations."
                        result = _tool_client.translate(prompt)
                        return result.translated.strip()
                    finally:
                        pass  # client 复用，不 close
            elif not cloud_only:
                # 本地 Ollama LLM 调用函数
                ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get("ollama_base_url", "http://localhost:11434")
                _tool_client = OllamaClient(
                    base_url=ollama_url,
                    model=agent_cfg.get("model", trans_cfg.get("model", "qwen3:8b")),
                    temperature=0.3,
                    num_predict=4096,
                    timeout=120.0,
                )
                def _llm_call_fn(prompt: str) -> str:
                    try:
                        _tool_client.system_prompt = "You are a helpful academic writing assistant. Follow the user's instructions precisely. Output ONLY the requested content, no explanations."
                        result = _tool_client.translate(prompt)
                        return result.translated.strip()
                    finally:
                        pass

            # 初始化论文模板 RAG 存储
            nonlocal _paper_rag
            _paper_rag = RAGStore(
                persist_dir=str(rag_dir),
                collection_name="paper_templates",
                chunk_size=rag_cfg.get("chunk_size", 512),
                chunk_overlap=rag_cfg.get("chunk_overlap", 64),
            )
            # 自动索引论文模板（仅在 collection 为空时）
            if _paper_rag.count_chunks() == 0:
                try:
                    from paper_assets import ingest_paper_assets as _ingest_pa
                    _ingest_pa(_paper_rag)
                except Exception as e:
                    logger.warning("论文模板自动索引失败（非致命）: %s", e)

            registry = create_default_registry(
                ollama_client=None if (use_cloud and cloud_key) else (_tool_client if not cloud_only else None),
                cloud_client=_tool_client if (use_cloud and cloud_key) else None,
                rag_store=_rag_store,
                paper_rag_store=_paper_rag,
                llm_call_fn=_llm_call_fn,
            )

            # 可选: 初始化时分复用调度器
            scheduler = None
            vram_cfg = agent_cfg.get("vram", {})
            if vram_cfg.get("enabled", True) and not cloud_only:
                scheduler = MultiplexingScheduler(
                    ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                    model=agent_cfg.get("model", "qwen3:8b"),
                )

            # 云端 API 配置（cloud_only 模式下必须，本地模式可选）
            cloud_cfg = trans_cfg.get("cloud", {})
            cloud_base_url = cloud_cfg.get("base_url", "")
            cloud_api_key = (cloud_cfg.get("api_key") or "").strip()
            cloud_model = cloud_cfg.get("model", "")

            # 从 provider preset 推断 API 格式
            provider = cloud_cfg.get("provider", "openai")
            preset = PROVIDER_PRESETS.get(provider, {})
            api_format = preset.get("api_format", "openai")

            memory_dir_val = str(RUNTIME_DIR / rag_cfg.get("memory_dir", "data/agent_memory"))
            _agent_instance = AgentLoop(
                ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                model=agent_cfg.get("model", "qwen3:8b"),
                tool_registry=registry,
                scheduler=scheduler,
                max_steps=agent_cfg.get("max_steps", 10),
                system_prompt=agent_cfg.get("system_prompt", ""),
                temperature=agent_cfg.get("temperature", 0.3),
                num_predict=agent_cfg.get("num_predict", 4096),
                timeout=trans_cfg.get("timeout", 300.0),
                cloud_base_url=cloud_base_url,
                cloud_api_key=cloud_api_key,
                cloud_model=cloud_model,
                api_format=api_format,
                memory_dir=memory_dir_val,
            )

            mode_label = "cloud" if _agent_instance._use_cloud else "local"
            fmt_label = f", format={api_format}" if _agent_instance._use_cloud else ""
            logger.info("Agent 初始化完成 (mode=%s%s, model=%s, rag=%s)",
                        mode_label, fmt_label, agent_cfg.get("model"), rag_dir)
            return _agent_instance

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        """Agent 对话端点 — SSE 流式返回 ReAct 推理过程。"""
        if not _AGENT_AVAILABLE:
            raise HTTPException(503, "Agent 模块未安装，请安装 chromadb")

        agent = await _get_agent()

        # cloud_only 模式需要云端 API Key 才能工作
        if cloud_only and not agent._use_cloud:
            raise HTTPException(
                503,
                "纯云端模式下 Agent 需要配置云端 API Key。"
                "请在前端设置中填写 API Key、Base URL 和模型名称。",
            )

        # 将历史消息转换为 Message 对象
        history: list[Message] | None = None
        if req.history:
            history = [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in req.history
            ]

        # 构建带上下文的完整消息
        full_message = req.message
        if req.context:
            full_message = f"[当前文档内容]\n{req.context}\n\n[用户问题]\n{req.message}"

        async def _stream() -> AsyncGenerator[dict, None]:
            async for event in agent.run(full_message, history):
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

    # ── 论文模板资源库端点 ──────────────────────────────────────────

    def _get_paper_rag() -> RAGStore:
        """懒加载 paper_templates collection 的 RAGStore。"""
        nonlocal _paper_rag
        if _paper_rag is None:
            config = _load_config()
            rag_cfg = config.get("agent", {}).get("rag", {})
            rag_dir = RUNTIME_DIR / rag_cfg.get("persist_dir", "data/chromadb")
            _paper_rag = RAGStore(
                persist_dir=str(rag_dir),
                collection_name="paper_templates",
                chunk_size=rag_cfg.get("chunk_size", 512),
                chunk_overlap=rag_cfg.get("chunk_overlap", 64),
            )
        return _paper_rag

    @app.get("/api/paper-assets/templates")
    async def list_paper_templates():
        """返回所有可用论文模板列表。"""
        from paper_assets import get_template_list
        return {"templates": get_template_list()}

    @app.get("/api/paper-assets/status")
    async def paper_assets_status():
        """返回论文模板索引状态。"""
        from paper_assets import get_ingestion_status
        return get_ingestion_status(_get_paper_rag())

    @app.post("/api/paper-assets/ingest")
    async def ingest_paper_assets():
        """手动触发论文模板资源索引。"""
        from paper_assets import ingest_paper_assets as _ingest
        result = _ingest(_get_paper_rag())
        return result

    @app.post("/api/paper-scaffold")
    async def generate_paper_scaffold(req: PaperScaffoldRequest):
        """生成论文骨架 Markdown。"""
        from paper_assets import generate_scaffold
        scaffold = generate_scaffold(
            template_id=req.template_id,
            title=req.title,
            sections=req.sections or None,
        )
        return {"markdown": scaffold, "template_id": req.template_id}

    @app.post("/api/paper-style-transfer")
    async def paper_style_transfer(req: StyleTransferRequest):
        """根据模板风格重写用户文本。"""
        from paper_assets import get_style_examples

        examples = get_style_examples(req.template_id, req.section)

        # 构造 prompt 让 LLM 参考范例重写
        config = _load_config()
        trans_cfg = config.get("translator", {})

        system_prompt = (
            "你是一位学术写作专家。请参考以下论文模板的风格范例，将用户提供的文本改写为符合该模板风格的版本。"
            "保持原文的核心内容和含义，但调整措辞、句式和表达方式以匹配模板风格。"
            "只输出改写后的文本，不要任何解释或注释。"
        )
        user_prompt = (
            f"目标模板: {req.template_id}\n"
            f"目标章节: {req.section}\n\n"
            f"风格范例:\n{examples}\n\n"
            f"请将以下文本改写为 {req.template_id} 风格:\n\n{req.text}"
        )

        # 使用翻译客户端作为通用 LLM
        try:
            if cloud_only or trans_cfg.get("engine") == "cloud":
                client = _build_cloud_client(trans_cfg, trans_cfg.get("cloud", {}))
                client.system_prompt = system_prompt
                result = client.translate(user_prompt)
                return {"text": result.translated.strip()}
            else:
                ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get(
                    "ollama_base_url", "http://localhost:11434"
                )
                client = OllamaClient(
                    base_url=ollama_url,
                    model=trans_cfg.get("model", "qwen3:8b"),
                    temperature=0.3,
                    num_predict=4096,
                    timeout=120.0,
                )
                client.system_prompt = system_prompt
                result = client.translate(user_prompt)
                return {"text": result.translated.strip()}
        except Exception as e:
            raise HTTPException(500, f"风格迁移失败: {e}")

    @app.on_event("shutdown")
    async def _shutdown():
        if _agent_instance is not None:
            await _agent_instance.close()

    return app
