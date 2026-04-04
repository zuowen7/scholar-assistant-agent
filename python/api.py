"""Scholar Translate FastAPI Server - 为 Tauri 前端提供 HTTP API"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.parser import extract_pages
from src.cleaner import clean_text_full
from src.chunker import chunk_text_full
from src.formatter import format_output
from src.translator.ollama_client import OllamaClient

app = FastAPI(title="Scholar Translate API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://localhost:5173",
        "http://localhost:18088",
        "tauri://localhost",
        "https://tauri.localhost",
    ],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
# Docker 环境通过环境变量切换配置，本地开发默认用 default.yaml
DOCKER_MODE = os.environ.get("DOCKER_MODE", "").lower() in ("1", "true", "yes")
CONFIG_PATH = (BASE_DIR / "config" / "docker.yaml") if DOCKER_MODE else (BASE_DIR / "config" / "default.yaml")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"

# 内存任务存储 (单用户桌面应用)
MAX_TASKS = 10
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB
tasks: dict[str, dict] = {}
is_busy = False


# --- Pydantic 模型 ---

class ConfigUpdate(BaseModel):
    chunker: dict | None = None
    translator: dict | None = None
    formatter: dict | None = None


class FilePathPayload(BaseModel):
    path: str


# --- 辅助函数 ---

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def _cleanup_tasks() -> None:
    """保留最近的 MAX_TASKS 条已完成/出错的任务"""
    if len(tasks) <= MAX_TASKS:
        return
    to_remove = [
        tid for tid, t in tasks.items()
        if t["status"] in ("done", "error")
    ]
    for tid in to_remove[:-MAX_TASKS]:
        del tasks[tid]


# --- 端点 ---

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/api/ollama/status")
def ollama_status():
    config = _load_config()
    trans_cfg = config.get("translator", {})
    client = OllamaClient(
        base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
    )
    return {"reachable": client.health_check()}


@app.post("/api/translate")
async def start_translate(file: UploadFile = File(...)):
    """上传 PDF 并创建翻译任务"""
    global is_busy

    if is_busy:
        raise HTTPException(409, "已有翻译任务在运行，请等待完成")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "仅支持 PDF 文件")

    task_id = uuid.uuid4().hex[:8]
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_path = INPUT_DIR / f"{task_id}_{file.filename}"
    with open(pdf_path, "wb") as f:
        total = 0
        while chunk := file.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_SIZE:
                pdf_path.unlink(missing_ok=True)
                raise HTTPException(413, "文件过大，最大支持 200 MB")
            f.write(chunk)

    tasks[task_id] = {
        "status": "pending",
        "pdf_path": str(pdf_path),
        "output_path": None,
        "content": None,
        "error": None,
    }

    return {"task_id": task_id}


@app.post("/api/translate/path")
async def start_translate_path(payload: FilePathPayload):
    """从本地文件路径创建翻译任务（供 Tauri 拖拽使用）"""
    global is_busy

    if is_busy:
        raise HTTPException(409, "已有翻译任务在运行，请等待完成")

    file_path = Path(payload.path)
    if not file_path.exists():
        raise HTTPException(400, "文件不存在")
    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    if file_path.stat().st_size > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "文件过大，最大支持 200 MB")

    task_id = uuid.uuid4().hex[:8]
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_path = INPUT_DIR / f"{task_id}_{file_path.name}"
    shutil.copy2(file_path, pdf_path)

    tasks[task_id] = {
        "status": "pending",
        "pdf_path": str(pdf_path),
        "output_path": None,
        "content": None,
        "error": None,
    }

    return {"task_id": task_id}


@app.get("/api/translate/{task_id}/stream")
async def translate_stream(task_id: str):
    """SSE 流: 返回翻译进度和结果"""
    if task_id not in tasks:
        raise HTTPException(404, f"任务 {task_id} 不存在")

    task = tasks[task_id]
    if task["status"] == "running":
        raise HTTPException(409, "该任务已在运行中")

    return EventSourceResponse(
        _run_pipeline(task_id),
        media_type="text/event-stream",
    )


async def _run_pipeline(task_id: str) -> AsyncGenerator[dict, None]:
    """执行完整的 5 步翻译管道，通过 SSE 推送进度"""
    global is_busy
    is_busy = True
    task = tasks[task_id]
    task["status"] = "running"

    try:
        config = _load_config()
        pdf_path = task["pdf_path"]

        # Step 1: 解析 PDF
        yield {
            "event": "progress",
            "data": json.dumps({"step": 1, "total": 5, "message": "解析 PDF..."}),
        }
        doc = await asyncio.to_thread(extract_pages, pdf_path)
        raw_text = doc.full_text
        dual_pages = sum(1 for p in doc.pages if p.is_dual_column)
        yield {
            "event": "parsed",
            "data": json.dumps({
                "pages": doc.page_count,
                "chars": len(raw_text),
                "dual_column_pages": dual_pages,
            }),
        }

        # Step 2: 清洗文本
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

        # Step 3: 切块
        yield {
            "event": "progress",
            "data": json.dumps({"step": 3, "total": 5, "message": "切块..."}),
        }
        chunker_cfg = config.get("chunker", {})
        chunk_result = await asyncio.to_thread(
            chunk_text_full,
            clean_result.text,
            chunker_cfg.get("max_tokens", 1024),
            chunker_cfg.get("overlap_tokens", 64),
            chunker_cfg.get("strategy", "sentence"),
            True,  # skip_references
        )
        yield {
            "event": "chunked",
            "data": json.dumps({
                "total_chunks": len(chunk_result.chunks),
                "references_chars": len(chunk_result.references_text),
            }),
        }

        # Step 4: 逐块翻译
        yield {
            "event": "progress",
            "data": json.dumps({"step": 4, "total": 5, "message": "翻译中..."}),
        }
        trans_cfg = config.get("translator", {})
        # BUG-02: 优先使用 OLLAMA_HOST 环境变量
        ollama_url = os.environ.get("OLLAMA_HOST") or trans_cfg.get("ollama_base_url", "http://localhost:11434")
        client = OllamaClient(
            base_url=ollama_url,
            model=trans_cfg.get("model", "qwen3:8b"),
            temperature=trans_cfg.get("temperature", 0.3),
            num_predict=trans_cfg.get("num_predict", 16384),
            system_prompt=trans_cfg.get("system_prompt", ""),
            timeout=trans_cfg.get("timeout", 300.0),
        )

        results = []
        total = len(chunk_result.chunks)
        for i, chunk in enumerate(chunk_result.chunks):
            result = await asyncio.to_thread(client.translate, chunk.text)
            results.append(result)
            yield {
                "event": "chunk_done",
                "data": json.dumps({
                    "index": i,
                    "total": total,
                    "original_preview": result.original[:200],
                    "translated_preview": result.translated[:200],
                    "tokens": result.completion_tokens,
                }),
            }

        # Step 5: 格式化输出
        yield {
            "event": "progress",
            "data": json.dumps({"step": 5, "total": 5, "message": "生成输出..."}),
        }
        fmt_cfg = config.get("formatter", {})
        content = format_output(
            results,
            output_format=fmt_cfg.get("output_format", "bilingual"),
        )
        if chunk_result.references_text:
            content += "\n\n---\n\n## References\n\n" + chunk_result.references_text

        output_path = OUTPUT_DIR / f"{task_id}_translated.md"
        output_path.write_text(content, encoding="utf-8")

        task["status"] = "done"
        task["output_path"] = str(output_path)
        task["content"] = content

        yield {
            "event": "complete",
            "data": json.dumps({
                "task_id": task_id,
                "output_path": str(output_path),
                "content": content,
                "chunks": [
                    {
                        "original": r.original,
                        "translated": r.translated,
                    }
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
        is_busy = False
        _cleanup_tasks()


@app.get("/api/config")
def get_config():
    return _load_config()


@app.put("/api/config")
def update_config(cfg: ConfigUpdate):
    current = _load_config()
    for section in ["chunker", "translator", "formatter"]:
        val = getattr(cfg, section)
        if val:
            current[section] = {**current.get(section, {}), **val}
    _save_config(current)
    return current


@app.get("/api/download/{task_id}")
def download_result(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "任务不存在")
    task = tasks[task_id]
    if task["status"] != "done" or not task.get("output_path"):
        raise HTTPException(400, "翻译尚未完成")
    path = Path(task["output_path"])
    if not path.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(
        path,
        filename=f"{task_id}_translated.md",
        media_type="text/markdown",
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scholar Translate API Server")
    parser.add_argument("--port", type=int, default=18088)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--static-dir", type=str, default=None,
                        help="前端静态文件目录 (Docker 部署用)")
    args = parser.parse_args()

    # Docker 模式: 挂载前端静态文件
    if args.static_dir:
        static_path = Path(args.static_dir)
        if static_path.exists():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
            print(f"[INFO] Serving frontend from {static_path}")

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
