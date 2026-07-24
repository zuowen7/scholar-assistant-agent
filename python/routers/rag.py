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


class IngestRequest(BaseModel):
    doc_id: str | None = None
    title: str | None = None
    text: str = Field(min_length=1, max_length=1_000_000)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    top_k: int = Field(default=5, ge=1, le=50)


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
    async def rag_list_documents():
        return list(_docs.values())

    @app.post("/api/rag/ingest")
    async def rag_ingest(req: IngestRequest):
        doc_id = req.doc_id or f"doc_{uuid.uuid4().hex[:8]}"
        entry = {
            "doc_id": doc_id,
            "title": req.title or doc_id,
            "text_length": len(req.text),
        }
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        try:
            async with _operation_lock:
                await asyncio.to_thread(
                    col.upsert,
                    ids=[doc_id],
                    documents=[req.text],
                    metadatas=[{"title": entry["title"]}],
                )
                _docs[doc_id] = entry
                await asyncio.to_thread(_save_docs)
        except Exception as e:
            logger.warning("RAG ingest to chromadb failed: %s", e)
            raise HTTPException(500, "RAG document ingest failed")

        return {"status": "ok", "doc_id": doc_id}

    @app.post("/api/rag/upload")
    async def rag_upload(file: UploadFile):
        content = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Uploaded document is too large (max 20 MB)")
        text = content.decode("utf-8", errors="replace")
        doc_id = f"upload_{uuid.uuid4().hex[:8]}"
        entry = {
            "doc_id": doc_id,
            "title": file.filename or doc_id,
            "text_length": len(text),
            "filename": file.filename,
        }
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        try:
            async with _operation_lock:
                await asyncio.to_thread(
                    col.upsert,
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[{"title": entry["title"]}],
                )
                _docs[doc_id] = entry
                await asyncio.to_thread(_save_docs)
        except Exception as e:
            logger.warning("RAG upload ingest to chromadb failed: %s", e)
            raise HTTPException(500, "RAG document ingest failed")

        return {"status": "ok", "doc_id": doc_id, "filename": file.filename}

    @app.delete("/api/rag/documents/{doc_id}")
    async def rag_delete_document(doc_id: str):
        if doc_id not in _docs:
            raise HTTPException(404, f"Document {doc_id} not found")
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        try:
            async with _operation_lock:
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
            results = await asyncio.to_thread(
                col.query, query_texts=[req.query], n_results=req.top_k
            )
            ids = (results.get("ids") or [[]])[0]
            documents = (results.get("documents") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            hits = []
            for index, doc_id in enumerate(ids):
                metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
                hits.append(
                    {
                        "doc_id": doc_id,
                        "source": metadata.get("title", doc_id),
                        "text": documents[index] if index < len(documents) else "",
                        "distance": distances[index] if index < len(distances) else None,
                        "metadata": metadata,
                    }
                )
            return {"hits": hits}
        except Exception as e:
            raise HTTPException(500, f"Query failed: {e}")

    return state
