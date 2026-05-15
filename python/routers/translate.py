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
from src.chunker import chunk_text_with_blocks
from src.formatter import format_blocks, format_output, HAS_PPTX
from src.translator.ollama_client import OllamaClient, TranslationResult
from src.translator.cloud_client import CloudClient, PROVIDER_PRESETS
from src.translator.context import extract_document_context
from src.translator.block_translator import (
    BlockTranslation,
    translate_block_chunks_parallel,
)
from src.translator.memory_store import TranslationMemory
from src.translator.glossary_store import GlossaryStore
from src.translator._helpers import restore_paragraphs_if_needed, _extract_term_pairs
from src.translator.post_qa import (
    run_post_translation_qa,
    get_hedging_tier_for_section,
)

logger = logging.getLogger(__name__)

# Fallback constants; overridden at runtime by config values (translate.max_tasks etc.)
_DEFAULT_MAX_TASKS = 10
_DEFAULT_MAX_UPLOAD_MB = 200
_DEFAULT_MAX_PDF_PAGES = 500
_RAG_INGEST_SEMAPHORE = asyncio.Semaphore(3)  # 最多 3 个并发 RAG 入库任务


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

    def _get_limits() -> tuple[int, int, int]:
        """Return (max_tasks, max_upload_bytes, max_pdf_pages) from runtime config."""
        cfg = load_config().get("translate", {})
        max_tasks = int(cfg.get("max_tasks", _DEFAULT_MAX_TASKS))
        max_upload_bytes = int(cfg.get("max_upload_mb", _DEFAULT_MAX_UPLOAD_MB)) * 1024 * 1024
        max_pdf_pages = int(cfg.get("max_pdf_pages", _DEFAULT_MAX_PDF_PAGES))
        return max_tasks, max_upload_bytes, max_pdf_pages

    def _cleanup_tasks() -> None:
        max_tasks, _, _ = _get_limits()
        done_ids = [tid for tid, t in tasks.items() if t["status"] in ("done", "error")]
        if len(done_ids) <= max_tasks:
            return
        excess = len(done_ids) - max_tasks
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
            # Expire stale tasks BEFORE checking has_running, so a stuck task
            # doesn't permanently block the slot.
            stale_running = [
                tid for tid, t in tasks.items()
                if t["status"] == "running"
                and tid != task_id
                and (time.monotonic() - t.get("_created_at", 0)) > 1800
            ]
            for tid in stale_running:
                logger.warning("Expiring stale running task %s (>30 min)", tid)
                tasks[tid]["status"] = "error"
                tasks[tid]["error"] = "任务超时（>30分钟）"
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
            has_running = any(
                t["status"] == "running"
                for tid, t in tasks.items()
                if tid != task_id
            )
            if has_running:
                raise HTTPException(409, "已有翻译任务在运行，请等待完成")

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

        # Reject if a running or pending task already exists
        has_active = any(
            t["status"] in ("running", "pending")
            for t in tasks.values()
        )
        if has_active:
            raise HTTPException(409, "已有翻译任务在运行，请等待完成")

        task_id = uuid.uuid4().hex[:8]
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        input_file = input_dir / f"{task_id}_{file.filename}"
        try:
            with open(input_file, "wb") as f:
                total = 0
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    _, max_upload_bytes, _ = _get_limits()
                    if total > max_upload_bytes:
                        input_file.unlink(missing_ok=True)
                        max_mb = max_upload_bytes // (1024 * 1024)
                        raise HTTPException(413, f"文件过大，最大支持 {max_mb} MB")
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
        _, max_upload_bytes, _ = _get_limits()
        if file_path.stat().st_size > max_upload_bytes:
            max_mb = max_upload_bytes // (1024 * 1024)
            raise HTTPException(413, f"文件过大，最大支持 {max_mb} MB")

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
                "event": "translate.progress",
                "data": json.dumps({"step": 1, "total": 5, "message": f"解析 {fmt_name}..."}),
            }

            # Use layout-aware extraction for PDFs to enable bilingual overlay export
            if ext == ".pdf":
                layout_doc, blocks = await asyncio.to_thread(extract_document_with_layout, input_path)
                doc = layout_doc
                _, _, max_pdf_pages = _get_limits()
                if doc.page_count > max_pdf_pages:
                    raise ValueError(
                        f"PDF 页数 ({doc.page_count}) 超过限制 ({max_pdf_pages} 页)，"
                        "请分割文件后重试。"
                    )
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

            # Article splitting: detect multi-article PDFs before cleaning
            from src.parser.article_detector import extract_articles
            raw_articles = await asyncio.to_thread(extract_articles, raw_text)
            num_articles = len(raw_articles)

            yield {
                "event": "translate.parsed",
                "data": json.dumps({
                    "pages": doc.page_count,
                    "chars": len(raw_text),
                    "dual_column_pages": dual_pages,
                    "block_count": len(blocks),
                    "articles": num_articles,
                }),
            }

            yield {
                "event": "translate.progress",
                "data": json.dumps({"step": 2, "total": 5, "message": "清洗文本..."}),
            }

            # Clean + chunk each article independently to prevent glossary pollution
            chunker_cfg = config.get("chunker", {})
            from src.chunker.splitter import Block, BlockChunk

            all_blocks: list[Block] = []
            all_chunks: list[BlockChunk] = []
            all_refs: list[str] = []
            total_clean_chars = 0
            has_any_refs = False

            for art_idx, raw_art in enumerate(raw_articles):
                art_clean = await asyncio.to_thread(clean_text_full, raw_art)
                total_clean_chars += len(art_clean.text)
                if art_clean.has_references:
                    has_any_refs = True
                if art_clean.references_text:
                    all_refs.append(art_clean.references_text)

                art_result = await asyncio.to_thread(
                    chunk_text_with_blocks,
                    art_clean.text,
                    chunker_cfg.get("max_tokens", 2048),
                    0,
                    True,
                )

                # Prefix block IDs with article index to avoid collisions
                if num_articles > 1:
                    for b in art_result.blocks:
                        b.id = f"a{art_idx}_{b.id}"
                    for c in art_result.chunks:
                        c.block_ids = [f"a{art_idx}_{bid}" for bid in c.block_ids]

                all_blocks.extend(art_result.blocks)
                all_chunks.extend(art_result.chunks)

            # Re-index chunks sequentially
            for ci, c in enumerate(all_chunks):
                c.index = ci

            # Build a unified BlockChunkResult
            from src.chunker.splitter import BlockChunkResult as BCR
            block_result = BCR(
                blocks=all_blocks,
                chunks=all_chunks,
                references_text="\n\n".join(all_refs),
            )

            yield {
                "event": "translate.cleaned",
                "data": json.dumps({
                    "chars": total_clean_chars,
                    "has_references": has_any_refs,
                    "articles": num_articles,
                }),
            }

            yield {
                "event": "translate.progress",
                "data": json.dumps({"step": 3, "total": 5, "message": "切块..."}),
            }

            blocks_by_id = {b.id: b for b in block_result.blocks}
            total_chunks = len(block_result.chunks)

            # 类型分布统计——用于前端显示和调试
            type_counts: dict[str, int] = {}
            for b in block_result.blocks:
                type_counts[b.type] = type_counts.get(b.type, 0) + 1

            yield {
                "event": "translate.chunked",
                "data": json.dumps({
                    "total_chunks": total_chunks,
                    "total_blocks": len(block_result.blocks),
                    "block_types": type_counts,
                    "references_chars": len(block_result.references_text),
                    # 完整块清单——前端可以预先渲染原文骨架
                    "blocks": [
                        {
                            "id": b.id,
                            "type": b.type,
                            "level": b.level,
                            "translatable": b.translatable,
                            "original": b.text,
                        }
                        for b in block_result.blocks
                    ],
                    "chunks": [
                        {
                            "index": c.index,
                            "block_ids": c.block_ids,
                            "char_count": c.char_count,
                            "estimated_tokens": c.estimated_tokens,
                        }
                        for c in block_result.chunks
                    ],
                }),
            }

            yield {
                "event": "translate.progress",
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
            # Persist for retry_block — same context as initial translation
            task["doc_context"] = doc_context or ""

            # Inject glossary prompt into client's system prompt
            if glossary_store and len(glossary_store) > 0:
                glossary_prompt = glossary_store.build_prompt_text()
                if glossary_prompt:
                    existing_sp = trans_cfg.get("system_prompt", "")
                    enhanced_sp = existing_sp + "\n\n" + glossary_prompt if existing_sp else glossary_prompt
                    if hasattr(client, "system_prompt"):
                        client.system_prompt = enhanced_sp

            fallback_count = 0
            misalign_count = 0
            parallel_cfg = trans_cfg.get("parallel", {})
            max_concurrency = parallel_cfg.get("max_concurrency", 1)

            src_lang = trans_cfg.get("source_lang", "en")
            tgt_lang = trans_cfg.get("target_lang", "zh")
            task["source_lang"] = src_lang
            task["target_lang"] = tgt_lang

            # 收集所有块的翻译结果（按 block_id 索引），便于后续重组
            block_trans_by_id: dict[str, BlockTranslation] = {}

            # TM 命中的 chunk（按 chunk.text 整体查询）
            tm_hit_chunks: dict[int, str] = {}  # chunk_index -> hit.target
            llm_chunks: list = []
            for chunk in block_result.chunks:
                hit = await asyncio.to_thread(
                    tm_store.lookup, chunk.text,
                    source_lang=src_lang, target_lang=tgt_lang,
                )
                if hit.match_type in ("exact", "fuzzy"):
                    tm_hit_chunks[chunk.index] = hit.target
                    yield {
                        "event": "translate.chunk_tm_hit",
                        "data": json.dumps({
                            "index": chunk.index,
                            "total": total_chunks,
                            "match_type": hit.match_type,
                            "score": round(hit.score, 3),
                            "original_preview": chunk.text[:200],
                            "translated_preview": hit.target[:200],
                        }),
                    }
                else:
                    llm_chunks.append(chunk)

            # TM 命中的 chunk：按块比例分配 hit.target
            from src.translator.block_translator import _align_translation_to_blocks
            for cidx, hit_target in tm_hit_chunks.items():
                chunk = next(c for c in block_result.chunks if c.index == cidx)
                blocks = [blocks_by_id[bid] for bid in chunk.block_ids]
                bts, _ = _align_translation_to_blocks(blocks, hit_target)
                for bt in bts:
                    block_trans_by_id[bt.block_id] = bt
                    yield {
                        "event": "translate.block_translated",
                        "data": json.dumps({
                            "chunk_index": cidx,
                            "block_id": bt.block_id,
                            "type": bt.type,
                            "translatable": bt.translatable,
                            "original": bt.original,
                            "translated": bt.translated,
                            "source": "tm",
                            "status": bt.status,
                        }),
                    }

            # 翻译剩余 chunk
            try:
                if llm_chunks:
                    async for cr in translate_block_chunks_parallel(
                        client,
                        llm_chunks,
                        blocks_by_id,
                        max_concurrency=max_concurrency,
                        source_lang=src_lang,
                    ):
                        if cr.error:
                            yield {
                                "event": "translate.chunk_error",
                                "data": json.dumps({
                                    "index": cr.chunk_index,
                                    "total": total_chunks,
                                    "error": cr.error,
                                }),
                            }
                        if cr.is_fallback:
                            fallback_count += 1
                        if not cr.aligned and not cr.is_fallback:
                            misalign_count += 1

                        # 发送每块翻译结果
                        for bt in cr.block_translations:
                            block_trans_by_id[bt.block_id] = bt
                            yield {
                                "event": "translate.block_translated",
                                "data": json.dumps({
                                    "chunk_index": cr.chunk_index,
                                    "block_id": bt.block_id,
                                    "type": bt.type,
                                    "translatable": bt.translatable,
                                    "original": bt.original,
                                    "translated": bt.translated,
                                    "aligned": cr.aligned,
                                    "status": bt.status,
                                }),
                            }

                        # Glossary 校验在 chunk 级（合并所有块的译文）
                        if glossary_store:
                            chunk_orig = "\n\n".join(bt.original for bt in cr.block_translations if bt.translatable)
                            chunk_trans = "\n\n".join(bt.translated for bt in cr.block_translations if bt.translatable)
                            violations = glossary_store.enforce(chunk_trans, original=chunk_orig)
                            if violations:
                                yield {
                                    "event": "translate.glossary_violation",
                                    "data": json.dumps({
                                        "index": cr.chunk_index,
                                        "total": total_chunks,
                                        "violations": violations,
                                    }),
                                }
                            learned = _extract_term_pairs(chunk_orig, chunk_trans)
                            if learned:
                                glossary_store.add_suggestions(learned)

                        # 翻译后 QA (P0): 过度宣称/句长/混用检测
                        chunk_trans_for_qa = "\n\n".join(
                            bt.translated for bt in cr.block_translations if bt.translatable
                        )
                        if chunk_trans_for_qa.strip():
                            hedging_tier = get_hedging_tier_for_section(cr.section_type)
                            qa_result = run_post_translation_qa(
                                translated=chunk_trans_for_qa,
                                section_type=cr.section_type,
                                source_lang=src_lang,
                                expected_hedging_tier=hedging_tier,
                            )
                            if qa_result.has_warnings:
                                yield {
                                    "event": "translate.qa_warnings",
                                    "data": json.dumps({
                                        "index": cr.chunk_index,
                                        "total": total_chunks,
                                        "section_type": cr.section_type,
                                        "score": qa_result.score,
                                        "flags": [
                                            {
                                                "type": f.type,
                                                "severity": f.severity,
                                                "location": f.location,
                                                "message": f.message,
                                                "suggestion": f.suggestion,
                                            }
                                            for f in qa_result.flags
                                        ],
                                    }),
                                }

                        # 兼容：发送 chunk_done 事件供旧前端 fallback
                        chunk_orig = "\n\n".join(bt.original for bt in cr.block_translations)
                        chunk_trans = "\n\n".join(bt.translated for bt in cr.block_translations)
                        yield {
                            "event": "translate.chunk_done",
                            "data": json.dumps({
                                "index": cr.chunk_index,
                                "total": total_chunks,
                                "original_preview": chunk_orig[:200],
                                "translated_preview": chunk_trans[:200],
                                "tokens": cr.completion_tokens,
                                "fallback": cr.is_fallback,
                                "aligned": cr.aligned,
                                "section_type": cr.section_type,
                            }),
                        }
            finally:
                if hasattr(client, "close"):
                    client.close()

            # 构造按原始块顺序的扁平翻译列表
            ordered_block_translations: list[BlockTranslation] = []
            for b in block_result.blocks:
                bt = block_trans_by_id.get(b.id)
                if bt is None:
                    # 未翻译（理论上不会发生，安全兜底）
                    bt = BlockTranslation(
                        block_id=b.id,
                        type=b.type,
                        original=b.text,
                        translated=b.text,
                        translatable=b.translatable,
                        status='ok',
                    )
                ordered_block_translations.append(bt)

            # 写入 TM：按 chunk 整体保存（保持向后兼容的 TM 结构）
            for chunk in llm_chunks:
                blocks = [blocks_by_id[bid] for bid in chunk.block_ids]
                chunk_orig = "\n\n".join(b.text for b in blocks)
                chunk_trans = "\n\n".join(
                    block_trans_by_id[b.id].translated for b in blocks
                    if b.id in block_trans_by_id
                )
                if chunk_orig and chunk_trans:
                    try:
                        await asyncio.to_thread(
                            tm_store.store, chunk_orig, chunk_trans,
                            source_lang=src_lang, target_lang=tgt_lang,
                        )
                    except Exception:
                        logger.debug("TM store failed for chunk %d (non-fatal)", chunk.index)

            yield {
                "event": "translate.progress",
                "data": json.dumps({"step": 5, "total": 5, "message": "生成输出..."}),
            }
            fmt_cfg = config.get("formatter", {})
            content = format_blocks(
                ordered_block_translations,
                output_format=fmt_cfg.get("output_format", "bilingual"),
            )

            out_path = output_dir / f"{task_id}_translated.md"
            out_path.write_text(content, encoding="utf-8")

            task["status"] = "done_with_warnings" if (fallback_count or misalign_count) else "done"
            task["fallback_count"] = fallback_count
            task["misalign_count"] = misalign_count
            task["output_path"] = str(out_path)
            task["block_translations"] = [
                {
                    "id": bt.block_id,
                    "type": bt.type,
                    "translatable": bt.translatable,
                    "original": bt.original,
                    "translated": bt.translated,
                    "status": bt.status,
                }
                for bt in ordered_block_translations
            ]
            # 兼容字段：保留旧 chunks 结构供未升级的前端使用
            task["chunks"] = [
                {
                    "original": "\n\n".join(b.text for b in (blocks_by_id[bid] for bid in c.block_ids)),
                    "translated": "\n\n".join(
                        block_trans_by_id[bid].translated
                        for bid in c.block_ids
                        if bid in block_trans_by_id
                    ),
                }
                for c in block_result.chunks
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
                        async with _RAG_INGEST_SEMAPHORE:
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
                    def _log_bg_exc(t: asyncio.Task) -> None:
                        if not t.cancelled() and t.exception():
                            logger.error("RAG 后台入库失败: %s", t.exception(), exc_info=t.exception())
                    _bg_task.add_done_callback(_log_bg_exc)
                    rag_ingested = True
            except Exception as rag_err:
                logger.warning("翻译结果入库 RAG 准备失败（不影响翻译）: %s", rag_err)

            yield {
                "event": "translate.complete",
                "data": json.dumps({
                    "task_id": task_id,
                    "output_path": str(out_path),
                    "content": content,
                    "rag_ingested": rag_ingested,
                    "block_ids": [b.block_id for b in task.get("blocks", []) or []] if task.get("blocks") else None,
                    # 结构化 blocks——前端按块渲染的核心数据
                    "blocks": task["block_translations"],
                    # 向后兼容的扁平 chunks
                    "chunks": task["chunks"],
                    "misalign_count": misalign_count,
                }),
            }

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)
            logger.exception("翻译管道异常")
            yield {
                "event": "translate.error",
                "data": json.dumps({"message": "翻译失败，请稍后重试"}),
            }
        finally:
            # If the generator exited abnormally (client disconnect, early exception),
            # the status may still be "running". Forcibly mark it done so the slot
            # is released for the next translation.
            if task.get("status") == "running":
                task["status"] = "error"
                if not task.get("error"):
                    task["error"] = "任务被中断或客户端断开连接"
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
            elif new_api_key and new_api_key != existing_cloud.get("api_key", ""):
                logger.info("[AUDIT] API key updated for provider=%s", cfg.cloud.get("provider", "unknown"))
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
        markdown_to_docx(content, str(out_docx), title="研墨双语对照导出")
        return FileResponse(
            out_docx,
            filename=f"{payload.task_id}_bilingual.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @app.post("/api/export/translation_only_docx")
    async def export_translation_only_docx(payload: BilingualPdfPayload):
        """导出纯译文Word文档（P2-1）"""
        if payload.task_id not in tasks:
            raise HTTPException(404, "任务不存在")
        t = tasks[payload.task_id]
        if t["status"] not in ("done", "done_with_warnings"):
            raise HTTPException(400, "翻译尚未完成")

        output_dir = data_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        block_translations = t.get("block_translations", [])
        if not block_translations:
            raise HTTPException(400, "未找到翻译结果")

        # 构建纯译文内容
        from src.formatter.word_exporter import markdown_to_docx
        parts = []
        for bt in block_translations:
            if bt.get("status") == "failed":
                continue
            if not bt.get("translatable"):
                parts.append(bt.get("original", ""))
            elif bt.get("translated"):
                trans = bt["translated"]
                # 移除标题标记
                if bt.get("type") == "heading":
                    level = bt.get("level", 2)
                    trans = trans.lstrip("#").strip()
                    parts.append(f"{'#' * min(max(level, 1), 6)} {trans}")
                else:
                    parts.append(trans)

        content = "\n\n".join(parts)
        out_docx = output_dir / f"{payload.task_id}_translation_only.docx"
        markdown_to_docx(content, str(out_docx), title="研墨纯译文导出")
        return FileResponse(
            out_docx,
            filename=f"{payload.task_id}_translation_only.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @app.post("/api/export/pptx")
    async def export_pptx(payload: BilingualPdfPayload):
        """导出 PPTX 演示文稿（P2: 借鉴 nature-paper2ppt）"""
        if not HAS_PPTX:
            raise HTTPException(400, "python-pptx 未安装，请运行: pip install python-pptx")

        if payload.task_id not in tasks:
            raise HTTPException(404, "任务不存在")
        t = tasks[payload.task_id]
        if t["status"] not in ("done", "done_with_warnings"):
            raise HTTPException(400, "翻译尚未完成")

        output_dir = data_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        block_translations = t.get("block_translations", [])
        if not block_translations:
            raise HTTPException(400, "未找到翻译结果")

        # 从翻译结果构建幻灯片数据
        slides_data: list[dict] = []
        current_section: dict | None = None

        for bt in block_translations:
            if bt.get("type") == "heading":
                # 新的章节
                if current_section and current_section.get("key_points"):
                    slides_data.append(current_section)
                current_section = {
                    "section_title": bt.get("translated") or bt.get("original", ""),
                    "key_points": [],
                    "notes": "",
                }
            elif current_section is not None:
                text = bt.get("translated") or bt.get("original", "")
                if text.strip():
                    # 截取前 200 字符作为要点
                    key_point = text.strip()[:200]
                    if len(text.strip()) > 200:
                        key_point += "..."
                    current_section["key_points"].append(key_point)

        # 不要忘记最后一个章节
        if current_section and current_section.get("key_points"):
            slides_data.append(current_section)

        if not slides_data:
            raise HTTPException(400, "无可导出的内容")

        from src.formatter.pptx_exporter import export_translated_paper_to_pptx
        out_pptx = output_dir / f"{payload.task_id}_presentation.pptx"
        export_translated_paper_to_pptx(
            out_pptx,
            title=t.get("title", "学术报告"),
            section_slides=slides_data,
        )
        return FileResponse(
            out_pptx,
            filename=f"{payload.task_id}_presentation.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    @app.post("/api/export/data_availability")
    async def export_data_availability(payload: BilingualPdfPayload):
        """生成 Data Availability 声明（P3: 借鉴 nature-data）"""
        if payload.task_id not in tasks:
            raise HTTPException(404, "任务不存在")
        t = tasks[payload.task_id]
        if t["status"] not in ("done", "done_with_warnings"):
            raise HTTPException(400, "翻译尚未完成")

        from src.formatter.data_availability import (
            DatasetInfo,
            AccessRoute,
            format_data_availability_section,
        )

        # 从翻译结果中提取可能与数据相关的 block
        block_translations = t.get("block_translations", [])
        data_sections: list[str] = []
        for bt in block_translations:
            text = (bt.get("translated") or bt.get("original", "")).lower()
            if any(kw in text for kw in [
                "data", "dataset", "数据", "repository", "available",
                "accession", "source data", "supplementary",
            ]):
                data_sections.append(bt.get("translated") or bt.get("original", ""))

        # 生成声明框架
        if data_sections:
            # 有相关内容 → 生成含待确认项的框架
            datasets = [
                DatasetInfo(
                    name="generated data",
                    access_route=AccessRoute.PUBLIC_REPO,
                    repository="",
                    identifier="",
                    description="raw and processed data supporting the findings",
                )
            ]
            section = format_data_availability_section(
                datasets=datasets,
                output_format="nature",
            )
        else:
            # 无相关内容 → 通用声明
            section = format_data_availability_section(output_format="nature")

        return {
            "section": section,
            "message": "请根据实际数据情况填写仓库名称、DOI/登录号等字段",
        }

    @app.post("/api/translate/{task_id}/retry_block")
    async def retry_block_translation(task_id: str, payload: dict):
        """重试单个失败块的翻译（与正常翻译同路径）"""
        if task_id not in tasks:
            raise HTTPException(404, "任务不存在")

        t = tasks[task_id]
        block_id = payload.get("block_id")
        if not block_id:
            raise HTTPException(400, "缺少 block_id 参数")

        block_translations = t.get("block_translations", [])
        target_block = None
        target_index = -1

        for i, bt in enumerate(block_translations):
            if bt.get("id") == block_id:
                target_block = bt
                target_index = i
                break

        if not target_block:
            raise HTTPException(404, "块不存在")

        original_text = (target_block.get("original") or "").strip()
        if not original_text:
            raise HTTPException(400, "块原文为空，无法重试")

        config = load_config()
        trans_cfg = config.get("translator", {})
        use_cloud = cloud_only or trans_cfg.get("engine", "ollama") == "cloud"

        if use_cloud:
            cloud_cfg = trans_cfg.get("cloud", {})
            key = (cloud_cfg.get("api_key") or "").strip()
            if not key:
                raise HTTPException(400, "未配置云端 API Key，请在配置中设置 translator.cloud.api_key")
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

        # Re-inject doc context + glossary so single-block retry has the same hints
        doc_context = t.get("doc_context") or ""
        if doc_context:
            client.set_document_context(doc_context)

        if glossary_store and len(glossary_store) > 0:
            glossary_prompt = glossary_store.build_prompt_text()
            if glossary_prompt:
                existing_sp = trans_cfg.get("system_prompt", "")
                enhanced_sp = (
                    existing_sp + "\n\n" + glossary_prompt if existing_sp else glossary_prompt
                )
                if hasattr(client, "system_prompt"):
                    client.system_prompt = enhanced_sp

        src_lang = t.get("source_lang") or trans_cfg.get("source_lang", "en")

        from src.translator._helpers import _sanitize_llm_output, _validate_translation

        try:
            result = await asyncio.to_thread(client.translate, original_text, "")
            # Sanitize and validate exactly like the main pipeline does
            sanitized = _sanitize_llm_output(result.translated, source_lang=src_lang)
            result.translated = sanitized

            ok = bool(sanitized) and sanitized.strip() != original_text.strip() and _validate_translation(result)

            if not ok:
                # Persist failed status so retry button stays visible
                block_translations[target_index]["translated"] = ""
                block_translations[target_index]["status"] = "failed"
                raise HTTPException(
                    422,
                    "重试结果未通过质量校验（译文为空 / 与原文相同 / 过短）。请检查模型或调小段落。",
                )

            block_translations[target_index]["translated"] = sanitized
            block_translations[target_index]["status"] = "ok"

            return {
                "success": True,
                "block_id": block_id,
                "translated": sanitized,
                "status": "ok",
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("重试块翻译异常 block_id=%s", block_id)
            block_translations[target_index]["status"] = "failed"
            raise HTTPException(500, "块重试失败，请稍后重试")
        finally:
            if hasattr(client, "close"):
                client.close()

    _state["tasks"] = tasks
    _state["tm_store"] = tm_store
    _state["glossary_store"] = glossary_store
    return _state
