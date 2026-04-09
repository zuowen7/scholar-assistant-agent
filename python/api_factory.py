"""FastAPI 应用工厂 — 本地(Ollama+云) 与 纯云端 两种模式"""

from __future__ import annotations

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

BASE_DIR = Path(__file__).parent
DOCKER_MODE = os.environ.get("DOCKER_MODE", "").lower() in ("1", "true", "yes")
CONFIG_PATH = (BASE_DIR / "config" / "docker.yaml") if DOCKER_MODE else (BASE_DIR / "config" / "default.yaml")

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


_config_cache: dict | None = None
_config_cache_mtime: float = 0.0
_CONFIG_CACHE_TTL = 2.0  # 秒


def _load_config() -> dict:
    global _config_cache, _config_cache_mtime
    if CONFIG_PATH.exists():
        mtime = CONFIG_PATH.stat().st_mtime
        if _config_cache is not None and (time.monotonic() - _config_cache_mtime) < _CONFIG_CACHE_TTL and mtime == getattr(_load_config, "_last_mtime", 0):
            return copy.deepcopy(_config_cache)
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
            _config_cache_mtime = time.monotonic()
            _load_config._last_mtime = mtime  # type: ignore[attr-defined]
            return copy.deepcopy(_config_cache)
    return {}


def _save_config(config: dict) -> None:
    global _config_cache, _config_cache_mtime
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    _config_cache = copy.deepcopy(config)
    _config_cache_mtime = time.monotonic()


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

    data_root = BASE_DIR / ("data_cloud" if cloud_only else "data")
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
    app = FastAPI(title=title, version="0.3.0")

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
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/api/health")
    def health():
        payload = {"status": "ok", "version": "0.3.0"}
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
        if _busy_lock.locked():
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

        if _busy_lock.locked():
            raise HTTPException(409, "已有翻译任务在运行，请等待完成")

        await _busy_lock.acquire()
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

    return app
