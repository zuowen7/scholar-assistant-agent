"""Translate pipeline routes — upload, stream, download, config, health."""

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
from typing import AsyncGenerator, Literal

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.parser import extract_document, SUPPORTED_EXTENSIONS
from src.parser.extractor import extract_document_with_layout
from src.cleaner import clean_text_full
from src.chunker import chunk_text_full
from src.formatter import format_output
from src.translator.ollama_client import OllamaClient, TranslationResult
from src.translator.cloud_client import CloudClient, PROVIDER_PRESETS
from src.translator.context import extract_document_context
from src.translator.parallel_runner import translate_chunks_parallel
from src.translator.memory_store import TranslationMemory
from src.translator.glossary_store import GlossaryStore
from src.translator._helpers import restore_paragraphs_if_needed, _extract_term_pairs

logger = logging.getLogger(__name__)

MAX_TASKS = 10
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB


class ConfigUpdate(BaseModel):
    chunker: dict | None = None
    translator: dict | None = None
    formatter: dict | None = None
    cloud: dict | None = None


class FilePathPayload(BaseModel):
    path: str = Field(max_length=1024)


class BilingualPdfPayload(BaseModel):
    task_id: str


def register_translate(
    app: FastAPI,
    *,
    cloud_only: bool,
    load_config,
    save_config,
    build_cloud_client,
    mask_api_key,
    is_masked,
    validate_file_path,
    runtime_dir: Path,
    rag_store_getter,
) -> dict:
    """Register translate/config/health routes. Returns shared state dict."""
    tasks: dict[str, dict] = {}
    _task_lock = asyncio.Lock()
    _state: dict = {"rag_store_getter": rag_store_getter}

    tm_store = TranslationMemory(runtime_dir / "tm.db")

    # Glossary store — load seed glossaries from data/translator/glossaries/
    glossary_store = GlossaryStore()
    glossary_dir = runtime_dir / "data" / "translator" / "glossaries"
    glossary_store.load_yaml_dir(glossary_dir)

    data_root = runtime_dir / ("data_cloud" if cloud_only else "data")
    input_dir = data_root / "input"
    output_dir = data_root / "output"

    def _cleanup_tasks() -> None:
        done_ids = [tid for tid, t in tasks.items() if t["status"] in ("done", "error")]
        if len(done_ids) <= MAX_TASKS:
            return
        excess = len(done_ids) - MAX_TASKS
        for tid in done_ids[:excess]:
            _remove_task_files(tid)
            del tasks[tid]

    def _remove_task_files(task_id: str) -> None:
        t = tasks.get(task_id)
        if not t:
            return
        for key in ("input_path", "output_path"):
            p = t.get(key)
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass

    async def _acquire_task_slot(task_id: str) -> None:
        """Reserve a translation slot. Only one running task at a time."""
        async with _task_lock:
            has_running = any(
                t["status"] == "running"
                for tid, t in tasks.items()
                if tid != task_id
            )
            if has_running:
                raise HTTPException(409, "已有翻译任务在运行，请等待完成")
            # Stale pending cleanup: if a pending task has no stream connected
            # within 30s, mark it as expired so the next task can proceed.
            stale_ids = [
                tid for tid, t in tasks.items()
                if t["status"] == "pending"
                and tid != task_id
                and (time.monotonic() - t.get("_created_at", 0)) > 30
            ]
            for tid in stale_ids:
                logger.warning("Expiring stale pending task %s", tid)
                tasks[tid]["status"] = "error"
                tasks[tid]["error"] = "任务超时未启动"

    def _mark_task_created(task_id: str) -> None:
        tasks[task_id]["_created_at"] = time.monotonic()

    @app.get("/api/health")
    def health():
        from src._version import __version__
        payload = {"status": "ok", "version": __version__}
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
        config = load_config()
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
        config = load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        if not cloud_cfg.get("api_key"):
            return {"reachable": False, "error": "未配置 API Key"}
        client = build_cloud_client(trans_cfg, cloud_cfg)
        reachable, error_detail = client.health_check_detail()
        return {"reachable": reachable, "error": error_detail}

    @app.get("/api/cloud/providers")
    def cloud_providers():
        return PROVIDER_PRESETS

    @app.post("/api/translate")
    async def start_translate(file: UploadFile = File(...)):
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
        try:
            with open(input_file, "wb") as f:
                total = 0
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_SIZE:
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
                "blocks": None,
                "layout_doc": None,
            }
            _mark_task_created(task_id)
            return {"task_id": task_id}
        except Exception:
            if task_id in tasks:
                tasks[task_id]["status"] = "error"
            raise
    @app.post("/api/translate/path")
    async def start_translate_path(payload: FilePathPayload):
        file_path = Path(payload.path).resolve()
        validate_file_path(file_path)
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
        try:
            shutil.copy2(file_path, in_path)

            tasks[task_id] = {
                "status": "pending",
                "input_path": str(in_path),
                "output_path": None,
                "content": None,
                "error": None,
                "blocks": None,
                "layout_doc": None,
            }
            _mark_task_created(task_id)
            return {"task_id": task_id}
        except Exception:
            if task_id in tasks:
                tasks[task_id]["status"] = "error"
            raise

    async def _run_pipeline(task_id: str) -> AsyncGenerator[dict, None]:
        task = tasks[task_id]
        task["status"] = "running"

        try:
            config = load_config()
            input_path = task["input_path"]

            ext = Path(input_path).suffix.lower()
            fmt_name = SUPPORTED_EXTENSIONS.get(ext, "文档")
            yield {
                "event": "progress",
                "data": json.dumps({"step": 1, "total": 5, "message": f"解析 {fmt_name}..."}),
            }

            # Use layout-aware extraction for PDFs to enable bilingual overlay export
            if ext == ".pdf":
                layout_doc, blocks = await asyncio.to_thread(extract_document_with_layout, input_path)
                doc = layout_doc
                task["blocks"] = blocks
                task["layout_doc"] = layout_doc
                block_ids_in_page = len(blocks)
            else:
                doc = await asyncio.to_thread(extract_document, input_path)
                blocks = []
                task["blocks"] = None
                task["layout_doc"] = None

            raw_text = doc.full_text
            dual_pages = sum(1 for p in doc.pages if getattr(p, "is_dual_column", False))
            yield {
                "event": "parsed",
                "data": json.dumps({
                    "pages": doc.page_count,
                    "chars": len(raw_text),
                    "dual_column_pages": dual_pages,
                    "block_count": len(blocks),
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
                client = build_cloud_client(trans_cfg, cloud_cfg)
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

            # Inject glossary prompt into client's system prompt
            if glossary_store and len(glossary_store) > 0:
                glossary_prompt = glossary_store.build_prompt_text()
                if glossary_prompt:
                    existing_sp = trans_cfg.get("system_prompt", "")
                    enhanced_sp = existing_sp + "\n\n" + glossary_prompt if existing_sp else glossary_prompt
                    if hasattr(client, "system_prompt"):
                        client.system_prompt = enhanced_sp

            results_by_idx: dict[int, TranslationResult] = {}
            fallback_count = 0
            total_chunks = len(chunk_result.chunks)
            parallel_cfg = trans_cfg.get("parallel", {})
            max_concurrency = parallel_cfg.get("max_concurrency", 1)

            src_lang = trans_cfg.get("source_lang", "en")
            tgt_lang = trans_cfg.get("target_lang", "zh")

            # TM lookup: separate chunks into TM-hits and LLM-needs
            tm_hit_map: dict[int, tuple] = {}
            llm_indices: list[int] = []
            llm_chunks: list = []
            for i, chunk in enumerate(chunk_result.chunks):
                hit = await asyncio.to_thread(
                    tm_store.lookup, chunk.text,
                    source_lang=src_lang, target_lang=tgt_lang,
                )
                if hit.match_type in ("exact", "fuzzy"):
                    tm_hit_map[i] = (hit, chunk)
                else:
                    llm_indices.append(i)
                    llm_chunks.append(chunk)

            # Yield TM hits first (in order)
            for i in sorted(tm_hit_map):
                hit, chunk = tm_hit_map[i]
                results_by_idx[i] = TranslationResult(
                    original=chunk.text,
                    translated=hit.target,
                    model="tm",
                )
                yield {
                    "event": "chunk_tm_hit",
                    "data": json.dumps({
                        "index": i,
                        "total": total_chunks,
                        "match_type": hit.match_type,
                        "score": round(hit.score, 3),
                        "original_preview": chunk.text[:200],
                        "translated_preview": hit.target[:200],
                    }),
                }

            # Translate remaining chunks via LLM
            try:
                if llm_chunks:
                    async for cr in translate_chunks_parallel(
                        client,
                        llm_chunks,
                        max_concurrency=max_concurrency,
                        retry_delay=parallel_cfg.get("retry_delay", 2.0),
                    ):
                        orig_idx = llm_indices[cr.index]
                        if cr.error:
                            yield {
                                "event": "chunk_error",
                                "data": json.dumps({
                                    "index": orig_idx,
                                    "total": total_chunks,
                                    "error": cr.error,
                                }),
                            }
                        if cr.is_fallback:
                            fallback_count += 1
                        results_by_idx[orig_idx] = cr.result

                        # Glossary enforcement on translated text
                        if glossary_store:
                            violations = glossary_store.enforce(
                                cr.result.translated,
                                original=cr.result.original,
                            )
                            if violations:
                                yield {
                                    "event": "glossary_violation",
                                    "data": json.dumps({
                                        "index": orig_idx,
                                        "total": total_chunks,
                                        "violations": violations,
                                    }),
                                }
                            # Feed learned term pairs as suggestions
                            learned = _extract_term_pairs(cr.result.original, cr.result.translated)
                            if learned:
                                glossary_store.add_suggestions(learned)

                        yield {
                            "event": "chunk_done",
                            "data": json.dumps({
                                "index": orig_idx,
                                "total": total_chunks,
                                "original_preview": cr.result.original[:200],
                                "translated_preview": cr.result.translated[:200],
                                "tokens": cr.result.completion_tokens,
                                "fallback": cr.is_fallback,
                            }),
                        }
            finally:
                if hasattr(client, "close"):
                    client.close()

            # Reconstruct results in original chunk order
            results = [results_by_idx[i] for i in range(total_chunks)]

            # Store LLM results in TM
            for idx in llm_indices:
                r = results_by_idx[idx]
                try:
                    await asyncio.to_thread(
                        tm_store.store, r.original, r.translated,
                        source_lang=src_lang, target_lang=tgt_lang,
                    )
                except Exception:
                    logger.debug("TM store failed for chunk %d (non-fatal)", idx)

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

            task["status"] = "done_with_warnings" if fallback_count else "done"
            task["fallback_count"] = fallback_count
            task["output_path"] = str(out_path)
            task["chunks"] = [
                {
                    "original": r.original,
                    "translated": restore_paragraphs_if_needed(r.original, r.translated),
                }
                for r in results
            ]

            rag_ingested = False
            try:
                _ensure_fn = _state.get("ensure_rag_store")
                rs = await _ensure_fn() if _ensure_fn else _state.get("rag_store_getter", lambda: None)()
                if rs is not None:
                    src_lang = config.get("translator", {}).get("source_lang", "en")
                    src_label = "英文" if src_lang == "en" else src_lang
                    dual_text = f"[原文]\n{clean_result.text}\n\n[译文]\n{content}"
                    _task_id_str = task_id
                    _filename = task["filename"]
                    logger.info("RAG ingest queued for trans_%s, text length=%d", _task_id_str, len(dual_text))

                    async def _bg_ingest():
                        try:
                            await asyncio.to_thread(
                                rs.ingest_document,
                                f"trans_{_task_id_str}",
                                dual_text,
                                {"title": f"[翻译] {_filename}", "source": "translation", "source_lang": src_label},
                            )
                            logger.info("翻译结果已自动入库 RAG: trans_%s", _task_id_str)
                        except Exception as exc:
                            logger.warning("翻译结果入库 RAG 失败: %s", exc)

                    _bg_task = asyncio.create_task(_bg_ingest())
                    _bg_task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
                    rag_ingested = True
            except Exception as rag_err:
                logger.warning("翻译结果入库 RAG 准备失败（不影响翻译）: %s", rag_err)

            yield {
                "event": "complete",
                "data": json.dumps({
                    "task_id": task_id,
                    "output_path": str(out_path),
                    "content": content,
                    "rag_ingested": rag_ingested,
                    "block_ids": [b.block_id for b in task.get("blocks", []) or []] if task.get("blocks") else None,
                    "chunks": [
                        {
                            "original": r.original,
                            "translated": restore_paragraphs_if_needed(r.original, r.translated),
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
            _cleanup_tasks()

    @app.get("/api/translate/{task_id}/stream")
    async def translate_stream(task_id: str):
        if task_id not in tasks:
            raise HTTPException(404, f"任务 {task_id} 不存在")

        t = tasks[task_id]
        if t["status"] == "running":
            raise HTTPException(409, "该任务已在运行中")

        if t["status"] not in ("pending", "error"):
            raise HTTPException(409, f"任务状态为 {t['status']}，无法重新启动")

        t["error"] = None  # clear stale error state before restart
        await _acquire_task_slot(task_id)
        pipeline = _run_pipeline(task_id)

        async def _wrapped() -> AsyncGenerator[dict, None]:
            try:
                async for event in pipeline:
                    yield event
            except Exception:
                tasks[task_id]["status"] = "error"
                raise

        return EventSourceResponse(
            _wrapped(),
            media_type="text/event-stream",
        )

    @app.get("/api/config")
    def get_config():
        config = copy.deepcopy(load_config())
        if cloud_only:
            config.setdefault("translator", {})["engine"] = "cloud"
        mask_api_key(config)
        return config

    @app.put("/api/config")
    def update_config(cfg: ConfigUpdate):
        current = load_config()
        for section in ["chunker", "translator", "formatter"]:
            val = getattr(cfg, section)
            if val:
                current[section] = {**current.get(section, {}), **val}
        if cfg.cloud:
            trans = current.setdefault("translator", {})
            existing_cloud = trans.get("cloud", {})
            new_api_key = cfg.cloud.get("api_key", "")
            if new_api_key and is_masked(new_api_key):
                cfg.cloud["api_key"] = existing_cloud.get("api_key", "")
            trans["cloud"] = {**existing_cloud, **cfg.cloud}
        if cloud_only:
            current.setdefault("translator", {})["engine"] = "cloud"
        save_config(current)
        out = copy.deepcopy(current)
        mask_api_key(out)
        if cloud_only:
            out.setdefault("translator", {})["engine"] = "cloud"
        return out

    @app.get("/api/download/{task_id}")
    def download_result(task_id: str):
        if task_id not in tasks:
            raise HTTPException(404, "任务不存在")
        t = tasks[task_id]
        if t["status"] not in ("done", "done_with_warnings") or not t.get("output_path"):
            raise HTTPException(400, "翻译尚未完成")
        path = Path(t["output_path"])
        if not path.exists():
            raise HTTPException(404, "文件已丢失")
        headers: dict[str, str] = {}
        if t["status"] == "done_with_warnings":
            headers["X-Translation-Warnings"] = str(t.get("fallback_count", 0))
        return FileResponse(
            path,
            filename=f"{task_id}_translated.md",
            media_type="text/markdown",
            headers=headers,
        )

    # ── TM API routes ──────────────────────────────────────────────

    @app.get("/api/tm/stats")
    def tm_stats():
        s = tm_store.stats()
        return {
            "total_pairs": s.total_pairs,
            "source_lang": s.source_lang,
            "target_lang": s.target_lang,
        }

    @app.post("/api/tm/import")
    async def tm_import(file: UploadFile = File(...)):
        if not file.filename:
            raise HTTPException(400, "文件名不能为空")
        if not file.filename.lower().endswith(".tmx"):
            raise HTTPException(400, "仅支持 TMX 格式文件")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".tmx", delete=False) as tmp:
            while chunk := file.file.read(1024 * 1024):
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            count = await asyncio.to_thread(tm_store.import_tmx, tmp_path)
            return {"imported": count}
        except Exception as e:
            raise HTTPException(400, f"TMX 导入失败: {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @app.get("/api/tm/export")
    async def tm_export(source_lang: str = "en", target_lang: str = "zh"):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".tmx", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            count = await asyncio.to_thread(
                tm_store.export_tmx, tmp_path,
                source_lang=source_lang, target_lang=target_lang,
            )
            return FileResponse(
                tmp_path,
                filename="translation_memory.tmx",
                media_type="application/xml",
            )
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            raise HTTPException(500, f"TMX 导出失败: {e}")

    # ── Glossary API routes ────────────────────────────────────────────

    @app.get("/api/glossary")
    def get_glossary():
        return {"entries": glossary_store.to_dict_list(), "total": len(glossary_store)}

    @app.put("/api/glossary")
    def update_glossary(payload: dict):
        items = payload.get("entries", [])
        if not isinstance(items, list):
            raise HTTPException(400, "entries must be a list")
        count = glossary_store.update_from_list(items)
        return {"entries": glossary_store.to_dict_list(), "total": count}

    @app.post("/api/glossary/import")
    async def glossary_import(
        file: UploadFile = File(...),
        locked: bool = False,
    ):
        if not file.filename:
            raise HTTPException(400, "文件名不能为空")
        ext = Path(file.filename).suffix.lower()
        if ext not in (".csv", ".tbx"):
            raise HTTPException(400, "仅支持 CSV 和 TBX 格式文件")

        import tempfile
        suffix = ext
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            while chunk := file.file.read(1024 * 1024):
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            if ext == ".csv":
                count = glossary_store.import_csv(tmp_path, locked=locked)
            else:
                count = glossary_store.import_tbx(tmp_path, locked=locked)
            return {"imported": count, "total": len(glossary_store)}
        except Exception as e:
            raise HTTPException(400, f"导入失败: {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @app.post("/api/export/bilingual_docx")
    async def export_bilingual_docx(payload: BilingualPdfPayload):
        if payload.task_id not in tasks:
            raise HTTPException(404, "任务不存在")
        t = tasks[payload.task_id]
        if t["status"] not in ("done", "done_with_warnings"):
            raise HTTPException(400, "翻译尚未完成")

        output_dir = data_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        raw_chunks = t.get("chunks", [])
        if not raw_chunks:
            raise HTTPException(400, "未找到翻译结果")

        from src.translator._helpers import TranslationResult
        results = [TranslationResult(**c) if isinstance(c, dict) else c for c in raw_chunks]

        from src.formatter import format_output
        fmt_cfg = {}
        content = format_output(results, output_format=fmt_cfg.get("output_format", "bilingual"))

        from src.formatter.word_exporter import markdown_to_docx
        out_docx = output_dir / f"{payload.task_id}_bilingual.docx"
        markdown_to_docx(content, str(out_docx), title="Scholar Assistant 双语对照导出")
        return FileResponse(
            out_docx,
            filename=f"{payload.task_id}_bilingual.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    _state["tasks"] = tasks
    _state["tm_store"] = tm_store
    _state["glossary_store"] = glossary_store
    return _state
