"""RAG (Retrieval-Augmented Generation) routes.

Endpoints:
  GET    /api/rag/documents              — list all ingested docs
  POST   /api/rag/ingest                 — ingest text by JSON
  POST   /api/rag/upload                 — upload file and ingest
  DELETE /api/rag/documents/{doc_id}     — delete a doc
  POST   /api/rag/query                  — semantic search
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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

    def _get_store():
        return _collection

    async def _ensure_store():
        nonlocal _chroma_client, _collection
        if _collection is not None:
            return _collection
        try:
            import chromadb
            _data_dir.mkdir(parents=True, exist_ok=True)
            _chroma_client = chromadb.PersistentClient(path=str(_data_dir))
            _collection = _chroma_client.get_or_create_collection("documents")
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
        _docs[doc_id] = entry

        col = await _ensure_store()
        if col is not None:
            try:
                col.add(
                    ids=[doc_id],
                    documents=[req.text],
                    metadatas=[{"title": entry["title"]}],
                )
            except Exception as e:
                logger.warning("RAG ingest to chromadb failed: %s", e)

        return {"status": "ok", "doc_id": doc_id}

    @app.post("/api/rag/upload")
    async def rag_upload(file: UploadFile):
        content = await file.read()
        text = content.decode("utf-8", errors="replace")
        doc_id = f"upload_{uuid.uuid4().hex[:8]}"
        entry = {
            "doc_id": doc_id,
            "title": file.filename or doc_id,
            "text_length": len(text),
            "filename": file.filename,
        }
        _docs[doc_id] = entry

        col = await _ensure_store()
        if col is not None:
            try:
                col.add(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[{"title": entry["title"]}],
                )
            except Exception as e:
                logger.warning("RAG upload ingest to chromadb failed: %s", e)

        return {"status": "ok", "doc_id": doc_id, "filename": file.filename}

    @app.delete("/api/rag/documents/{doc_id}")
    async def rag_delete_document(doc_id: str):
        if doc_id not in _docs:
            raise HTTPException(404, f"Document {doc_id} not found")
        del _docs[doc_id]

        col = await _ensure_store()
        if col is not None:
            try:
                col.delete(ids=[doc_id])
            except Exception:
                pass

        return {"status": "ok", "deleted": doc_id}

    @app.post("/api/rag/query")
    async def rag_query(req: QueryRequest):
        col = await _ensure_store()
        if col is None:
            raise HTTPException(503, "RAG store not available")
        try:
            results = col.query(query_texts=[req.query], n_results=req.top_k)
            return results
        except Exception as e:
            raise HTTPException(500, f"Query failed: {e}")

    return state
