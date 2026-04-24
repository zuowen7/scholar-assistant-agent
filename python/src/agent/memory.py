"""Simple file-backed memory for Agent events."""

from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any


class AgentMemory:
    def __init__(self, persist_dir: str) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.persist_dir / "memory.jsonl"

    def add(
        self,
        content: str,
        category: str = "general",
        importance: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "content": content,
            "category": category,
            "importance": importance,
            "tags": tags or [],
            "metadata": metadata or {},
            "created_at": time(),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
