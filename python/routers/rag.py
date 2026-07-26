"""RAG (Retrieval-Augmented Generation) routes.

Endpoints:
  GET    /api/rag/documents              — list all ingested docs
  POST   /api/rag/ingest                 — ingest text by JSON
  POST   /api/rag/upload                 — upload file and ingest
  DELETE /api/rag/documents/{doc_id}     — delete a doc
  POST   /api/rag/query                  — semantic search
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_CHUNK_TARGET_CHARS = 1400
_CHUNK_OVERLAP_CHARS = 180


class IngestRequest(BaseModel):
    doc_id: str | None = None
    title: str | None = None
    text: str = Field(min_length=1, max_length=1_000_000)
    project_root: str | None = Field(default=None, max_length=2000)
    source_id: str | None = Field(default=None, max_length=128)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    top_k: int = Field(default=5, ge=1, le=50)
    project_root: str | None = Field(default=None, max_length=2000)
    source_ids: list[str] | None = Field(default=None, max_length=100)


def _chunk_text(
    text: str,
    *,
    target_chars: int = _CHUNK_TARGET_CHARS,
    overlap_chars: int = _CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Split extracted prose into stable retrieval chunks without losing paragraph context."""
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n")]
    paragraphs = [part for part in paragraphs if part]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = [
            paragraph[index : index + target_chars]
            for index in range(0, len(paragraph), target_chars)
        ] or [paragraph]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if current and len(candidate) > target_chars:
                chunks.append(current)
                prefix = current[-overlap_chars:].lstrip()
                current = f"{prefix}\n\n{piece}".strip()
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def register_rag_routes(
    app: FastAPI,
    *,
    runtime_dir: Path,
) -> dict[str, Any]:
    """Register RAG endpoints. Returns state dict with get/ensure helpers."""
    _docs: dict[str, dict] = {}
    _chroma_client = None
    _collection = None
    _data_dir = runtime_dir / "data" / "chromadb"
    _docs_path = _data_dir / "documents.json"
    _store_lock = asyncio.Lock()
    _operation_lock = asyncio.Lock()

    if _docs_path.is_file():
        try:
            raw_docs = json.loads(_docs_path.read_text(encoding="utf-8"))
            if isinstance(raw_docs, dict):
                _docs.update({str(k): v for k, v in raw_docs.items() if isinstance(v, dict)})
        except (OSError, json.JSONDecodeError):
            logger.warning("RAG metadata index could not be loaded", exc_info=True)

    def _save_docs() -> None:
        _data_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=_data_dir, prefix=".documents.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_docs, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, _docs_path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def _get_store():
        return _collection

    async def _ensure_store():
        nonlocal _chroma_client, _collection
        if _collection is not None:
            return _collection
        async with _store_lock:
            if _collection is not None:
                return _collection
            try:
                import chromadb

                def _open_store():
                    _data_dir.mkdir(parents=True, exist_ok=True)
                    client = chromadb.PersistentClient(path=str(_data_dir))
                    return client, client.get_or_create_collection("documents")

                _chroma_client, _collection = await asyncio.to_thread(_open_store)
            except Exception as e:
                logger.warning("RAG store init failed: %s", e)
        return _collection

    state: dict[str, Any] = {
        "get_rag_store": _get_store,
        "ensure_rag_store": _ensure_store,
    }

    @app.get("/api/rag/documents")
    async def rag_list_documents(project_root: str | None = None):
        documents = list(_docs.values())
        if project_root is not None:
            documents = [item for item in documents if item.get("project_root") == project_root]
        return documents

    async def _ingest(
        *,
        doc_id: str,
        title: str,
        text: str,
        project_root: str | None = None,
        source_id: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        chunks = _chunk_text(text)
        if not chunks:
            raise HTTPException(422, "Document has no extractable text")
        entry = {
            "doc_id": doc_id,
            "title": title,
            "text_length": len(text),
            "chunk_count": len(chunks),
            "project_root": project_root,
            "source_id": source_id,
            "filename": filename,
        }
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        ids = [f"{doc_id}::{index}" for index in range(len(chunks))]
        metadatas = []
        for index in range(len(chunks)):
            metadata: dict[str, str | int] = {
                "doc_id": doc_id,
                "title": title,
                "chunk_index": index,
            }
            if project_root is not None:
                metadata["project_root"] = project_root
            if source_id is not None:
                metadata["source_id"] = source_id
            metadatas.append(metadata)
        try:
            async with _operation_lock:
                # Remove stale chunks when a source is re-indexed with different boundaries.
                await asyncio.to_thread(col.delete, where={"doc_id": doc_id})
                await asyncio.to_thread(
                    col.upsert,
                    ids=ids,
                    documents=chunks,
                    metadatas=metadatas,
                )
                _docs[doc_id] = entry
                await asyncio.to_thread(_save_docs)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("RAG ingest to chromadb failed: %s", exc)
            raise HTTPException(500, "RAG document ingest failed")
        return entry

    @app.post("/api/rag/ingest")
    async def rag_ingest(req: IngestRequest):
        doc_id = req.doc_id or f"doc_{uuid.uuid4().hex[:8]}"
        entry = await _ingest(
            doc_id=doc_id,
            title=req.title or doc_id,
            text=req.text,
            project_root=req.project_root,
            source_id=req.source_id,
        )
        return {
            "status": "ok",
            "doc_id": doc_id,
            "chunk_count": entry["chunk_count"],
        }

    @app.post("/api/rag/upload")
    async def rag_upload(file: UploadFile):
        from src.parser import SUPPORTED_EXTENSIONS, extract_document

        content = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Uploaded document is too large (max 20 MB)")
        filename = Path(file.filename or "source").name
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(415, f"Unsupported document format: {extension or 'unknown'}")
        if not content:
            raise HTTPException(422, "Uploaded document is empty")
        temp_path: Path | None = None
        try:
            fd, temp_name = tempfile.mkstemp(suffix=extension)
            temp_path = Path(temp_name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
            document = await asyncio.to_thread(extract_document, temp_path)
            text = document.full_text.strip()
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("RAG upload parse failed for %s: %s", filename, exc)
            raise HTTPException(422, "Uploaded document could not be parsed")
        finally:
            if temp_path is not None:
                with contextlib.suppress(OSError):
                    temp_path.unlink()
        if not text:
            raise HTTPException(422, "Uploaded document has no extractable text")
        doc_id = f"upload_{uuid.uuid4().hex[:8]}"
        entry = await _ingest(
            doc_id=doc_id,
            title=filename,
            text=text,
            filename=filename,
        )
        return {
            "status": "ok",
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": entry["chunk_count"],
        }

    @app.delete("/api/rag/documents/{doc_id}")
    async def rag_delete_document(doc_id: str):
        if doc_id not in _docs:
            raise HTTPException(404, f"Document {doc_id} not found")
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        try:
            async with _operation_lock:
                await asyncio.to_thread(col.delete, where={"doc_id": doc_id})
                # Compatibility with documents indexed before chunking was introduced.
                await asyncio.to_thread(col.delete, ids=[doc_id])
                del _docs[doc_id]
                await asyncio.to_thread(_save_docs)
        except Exception as e:
            logger.warning("RAG delete failed: %s", e)
            raise HTTPException(500, "RAG document delete failed")

        return {"status": "ok", "deleted": doc_id}

    @app.post("/api/rag/query")
    async def rag_query(req: QueryRequest):
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        try:
            where: dict[str, Any] | None = None
            filters: list[dict[str, Any]] = []
            if req.project_root is not None:
                filters.append({"project_root": req.project_root})
            if req.source_ids:
                filters.append({"source_id": {"$in": req.source_ids}})
            if len(filters) == 1:
                where = filters[0]
            elif filters:
                where = {"$and": filters}
            query_kwargs: dict[str, Any] = {
                "query_texts": [req.query],
                "n_results": req.top_k,
            }
            if where is not None:
                query_kwargs["where"] = where
            results = await asyncio.to_thread(
                col.query,
                **query_kwargs,
            )
            ids = (results.get("ids") or [[]])[0]
            documents = (results.get("documents") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            hits = []
            for index, chunk_id in enumerate(ids):
                metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
                hits.append(
                    {
                        "doc_id": metadata.get("doc_id", chunk_id),
                        "chunk_id": chunk_id,
                        "source": metadata.get("title", chunk_id),
                        "text": documents[index] if index < len(documents) else "",
                        "distance": distances[index] if index < len(distances) else None,
                        "metadata": metadata,
                    }
                )
            return {"hits": hits}
        except Exception as exc:
            logger.warning("RAG query failed: %s", exc)
            raise HTTPException(500, "RAG query failed")

    return state
