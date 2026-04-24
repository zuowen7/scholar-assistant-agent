"""Small persistent text store used by Agent and template search."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RAGDocument:
    id: str
    title: str
    chunk_count: int
    metadata: dict[str, Any]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", text.lower()))


class RAGStore:
    def __init__(
        self,
        persist_dir: str,
        collection_name: str = "scholar_docs",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", collection_name)
        self.path = self.persist_dir / f"{safe_name}.json"
        self.chunk_size = max(128, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        self._items: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")

    def _chunk_text(self, text: str) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        chunks: list[str] = []
        current = ""
        for para in paragraphs or [text]:
            if len(current) + len(para) + 2 <= self.chunk_size:
                current = f"{current}\n\n{para}".strip()
            else:
                if current:
                    chunks.append(current)
                current = para
                while len(current) > self.chunk_size:
                    chunks.append(current[: self.chunk_size])
                    start = self.chunk_size - self.chunk_overlap
                    current = current[start:]
        if current:
            chunks.append(current)
        return chunks

    def ingest_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> int:
        self.delete_document(doc_id, save=False)
        metadata = metadata or {}
        chunks = self._chunk_text(text)
        title = str(metadata.get("title") or doc_id)
        for index, chunk in enumerate(chunks):
            self._items.append(
                {
                    "doc_id": doc_id,
                    "title": title,
                    "index": index,
                    "text": chunk,
                    "metadata": metadata,
                }
            )
        self._save()
        return len(chunks)

    def retrieve_context(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q_tokens = _tokens(query)
        if not q_tokens:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._items:
            item_tokens = _tokens(item.get("text", ""))
            if not item_tokens:
                continue
            overlap = len(q_tokens & item_tokens)
            score = overlap / math.sqrt(len(item_tokens))
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "text": item["text"],
                "metadata": item.get("metadata", {}),
                "distance": max(0.0, 1.0 - score),
                "doc_id": item.get("doc_id"),
                "title": item.get("title", ""),
            }
            for score, item in scored[:top_k]
        ]

    def list_documents(self) -> list[RAGDocument]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in self._items:
            doc_id = item["doc_id"]
            grouped.setdefault(
                doc_id,
                {
                    "id": doc_id,
                    "title": item.get("title", doc_id),
                    "chunk_count": 0,
                    "metadata": item.get("metadata", {}),
                },
            )
            grouped[doc_id]["chunk_count"] += 1
        return [RAGDocument(**value) for value in grouped.values()]

    def delete_document(self, doc_id: str, save: bool = True) -> None:
        self._items = [item for item in self._items if item.get("doc_id") != doc_id]
        if save:
            self._save()

    def count_chunks(self) -> int:
        return len(self._items)
