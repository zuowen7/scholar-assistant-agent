"""Editor-related routes — edit, complete, export, vision, citation, zotero, images, paper."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)


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


class WordExportRequest(BaseModel):
    content: str
    title: str = "Scholar Assistant Export"


class CitationIndexRequest(BaseModel):
    content: str
    bibliography: list[dict] = []
    style: str = "ieee"


class ZoteroSearchRequest(BaseModel):
    query: str
    item_type: str | None = None
    limit: int = 20


class PaperScaffoldRequest(BaseModel):
    template_id: str = "generic_article"
    title: str = ""
    sections: list[str] | None = None


class PaperStyleTransferRequest(BaseModel):
    text: str = ""
    template_id: str = "generic_article"
    section: str = "introduction"


def register_editor(
    app: FastAPI,
    *,
    cloud_only: bool,
    load_config,
    runtime_dir: Path,
    data_root: Path,
    get_agent,
) -> None:
    """Register editor-related routes."""
    output_dir = data_root / "output"

    @app.post("/api/edit")
    async def edit_text(req: EditRequest):
        text = req.text or ""
        instruction = (req.instruction or "").strip()
        task_type = (req.task_type or "").lower()

        if not instruction:
            return EventSourceResponse(
                _edit_echo(text), media_type="text/event-stream"
            )

        config = load_config()
        trans_cfg = config.get("translator", {})
        engine = trans_cfg.get("engine", "ollama")

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
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                full_content += token
                                yield {"event": "delta", "data": json.dumps({"content": full_content}, ensure_ascii=False)}
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error("Edit cloud stream error: %s", e)
            if not full_content:
                full_content = f"AI 处理失败（云端 API 错误）: {e}"

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
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                full_content += token
                                yield {"event": "delta", "data": json.dumps({"content": full_content}, ensure_ascii=False)}
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error("Edit Ollama stream error: %s", e)
            if not full_content:
                full_content = f"AI 处理失败（Ollama 未启动？）: {e}"

        yield {"event": "delta", "data": json.dumps({"content": full_content}, ensure_ascii=False)}

    @app.post("/api/complete")
    async def complete_text(req: CompletionRequest):
        context = (req.context or "").strip()
        if not context:
            return {"completion": "", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

        config = load_config()
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
        agent = await get_agent()
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

    @app.post("/api/compliance")
    async def compliance_check(req: ComplianceRequest):
        try:
            from src.compliance.checker import ComplianceChecker
            checker = ComplianceChecker()
            report = checker.check(
                markdown=req.markdown,
                title=req.title,
                venue=req.venue,
                required_sections=req.required_sections.split(",") if req.required_sections else [],
            )
            return {"report": report}
        except Exception as e:
            return {"error": str(e), "report": None}

    @app.post("/api/export/word")
    async def export_word(req: WordExportRequest):
        from src.formatter.word_exporter import markdown_to_docx
        output_dir.mkdir(parents=True, exist_ok=True)
        docx_path = output_dir / f"export_{uuid.uuid4().hex[:8]}.docx"
        markdown_to_docx(req.content, docx_path, title=req.title)
        return {
            "path": str(docx_path),
            "filename": docx_path.name,
            "size": docx_path.stat().st_size,
        }

    @app.get("/api/export/word/{filename}")
    async def download_word(filename: str):
        safe_dir = runtime_dir / "data" / "output"
        safe_path = (safe_dir / filename).resolve()
        if not str(safe_path).startswith(str(safe_dir.resolve())):
            raise HTTPException(403, "禁止访问该文件")
        if not safe_path.exists() or safe_path.suffix.lower() != ".docx":
            raise HTTPException(404, "文件不存在")
        age_minutes = (time.time() - safe_path.stat().st_mtime) / 60
        if age_minutes > 30:
            safe_path.unlink(missing_ok=True)
            raise HTTPException(404, "文件已过期")
        return FileResponse(
            str(safe_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
        )

    @app.post("/api/upload/image")
    async def upload_image(file: UploadFile = File(...)):
        allowed_types = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
        if file.content_type not in allowed_types:
            raise HTTPException(400, f"不支持的图片格式: {file.content_type}")
        assets_dir = data_root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename).suffix.lower() if file.filename else ".png"
        filename = f"{uuid.uuid4().hex[:12]}{ext}"
        file_path = assets_dir / filename
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "图片大小超过 50MB 限制")
        with open(file_path, "wb") as f:
            f.write(content)
        relative_path = f"/api/assets/{filename}"
        return {
            "path": str(file_path),
            "filename": filename,
            "url": relative_path,
            "size": len(content),
        }

    @app.get("/api/assets/{filename}")
    async def serve_asset(filename: str):
        assets_dir = data_root / "assets"
        safe_path = (assets_dir / filename).resolve()
        if not str(safe_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(403, "禁止访问该文件")
        if not safe_path.exists():
            raise HTTPException(404, "文件不存在")
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

    @app.post("/api/vision/analyze")
    async def analyze_image(
        file: UploadFile = File(...),
        analysis_type: str = "general",
    ):
        assets_dir = data_root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename).suffix.lower() if file.filename else ".png"
        temp_filename = f"vision_{uuid.uuid4().hex[:12]}{ext}"
        temp_path = assets_dir / temp_filename
        content = await file.read()
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "图片大小超过 20MB 限制")
        with open(temp_path, "wb") as f:
            f.write(content)
        try:
            from src.mcp.vision_client import VisionClient
            client = VisionClient()
            result = await client.analyze_image(temp_path, analysis_type=analysis_type)
            return result.to_dict()
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except PermissionError:
                logger.warning("Vision temporary file is still locked, skip cleanup: %s", temp_path)

    @app.post("/api/vision/ocr")
    async def ocr_image(file: UploadFile = File(...)):
        return await analyze_image(file, analysis_type="general")

    @app.post("/api/vision/chart")
    async def analyze_chart(file: UploadFile = File(...)):
        return await analyze_image(file, analysis_type="chart")

    @app.post("/api/vision/table")
    async def extract_table(file: UploadFile = File(...)):
        return await analyze_image(file, analysis_type="table")

    @app.put("/api/citation/index")
    async def index_citations(req: CitationIndexRequest):
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
        from src.citation.indexer import CitationIndexer
        indexer = CitationIndexer()
        keys = indexer.extract_citations(content)
        index = indexer.build_index(content)
        return {
            "keys": keys,
            "unique_count": len(index),
            "index": index,
        }

    @app.get("/api/zotero/status")
    async def zotero_status():
        try:
            from src.zotero.client import ZoteroClient
            client = ZoteroClient()
            if not client.api_key or not client.user_id:
                return {"connected": False, "message": "未配置 Zotero API Key 或 User ID"}
            return {"connected": True, "user_id": client.user_id, "style": client.style}
        except Exception as e:
            return {"connected": False, "message": str(e)}

    @app.post("/api/zotero/search")
    async def search_zotero(req: ZoteroSearchRequest):
        try:
            from src.zotero.client import ZoteroClient
            client = ZoteroClient()
            items = client.search(query=req.query, item_type=req.item_type, limit=req.limit)
            return {"count": len(items), "items": [item.to_dict() for item in items]}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            logger.error("Zotero 搜索失败: %s", e)
            raise HTTPException(500, f"Zotero 搜索失败: {e}")

    @app.get("/api/zotero/item/{item_key}")
    async def get_zotero_item(item_key: str):
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
        try:
            from src.zotero.client import ZoteroClient
            client = ZoteroClient()
            item = client.get_item(item_key)
            if not item:
                raise HTTPException(404, f"文献不存在: {item_key}")
            return {"key": item_key, "bibtex": item.to_bibtex()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("导出 BibTeX 失败: %s", e)
            raise HTTPException(500, f"导出失败: {e}")

    @app.post("/api/zotero/export")
    async def export_zotero_bibtex(item_keys: list[str] | None = None):
        try:
            from src.zotero.client import ZoteroClient
            client = ZoteroClient()
            bibtex = client.export_bibtex(item_keys)
            return {"bibtex": bibtex, "count": len(bibtex.split("\n\n")) if bibtex else 0}
        except Exception as e:
            logger.error("导出 BibTeX 失败: %s", e)
            raise HTTPException(500, f"导出失败: {e}")

    @app.post("/api/zotero/citations")
    async def get_zotero_citations(item_keys: list[str]):
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
