"""持久化记忆系统 — MEMORY.md + SQLite 双层存储。

设计参考 Hermes Agent 的"内外双驱"记忆架构：
- 内部静态层：MEMORY.md 文件，记录长期事实（用户偏好、项目背景、关键约束）
- 外部动态层：SQLite 数据库，存储对话历史和轨迹摘要

记忆召回策略：
- 每次对话前，从 MEMORY.md 加载长期记忆
- SQLite 按语义关键词检索相关的历史对话摘要
- 注入方式：用 <memory-context> 标签包裹，避免与当前对话混淆
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from time import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_MAX_CHARS = 3000


@dataclass
class MemoryEntry:
    """一条记忆记录。

    Attributes:
        id: 记录唯一 ID。
        content: 记忆内容文本。
        category: 分类（fact/preference/experience/skill_reference）。
        source: 来源（user_input/review/manual）。
        created_at: 创建时间。
        importance: 重要性评分（0.0 ~ 1.0）。
    """

    id: int = 0
    content: str = ""
    category: str = "fact"
    source: str = "manual"
    created_at: str = ""
    importance: float = 0.5


class MemoryManager:
    """持久化记忆管理器。

    双层存储：
    1. MEMORY.md — 人工可编辑的长期事实文件，轻量透明
    2. SQLite — 结构化记忆条目，支持检索和评分

    Attributes:
        data_dir: 数据持久化目录。
        memory_file: MEMORY.md 文件路径。
    """

    def __init__(self, data_dir: str | Path = "data/agent", rag_store: Any | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.data_dir / "MEMORY.md"
        self._db_path = self.data_dir / "memory.db"
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._rag_store = rag_store  # 可选向量搜索后端（RAGStore，使用独立 collection）
        self._init_db()

    # ------------------------------------------------------------------
    # SQLite 初始化
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """返回当前线程的 SQLite 连接（WAL 模式，每线程独立）。"""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        """初始化 SQLite 表结构。"""
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'fact',
                source TEXT NOT NULL DEFAULT 'manual',
                importance REAL NOT NULL DEFAULT 0.5
                    CHECK (importance >= 0.0 AND importance <= 1.0),
                created_at TEXT NOT NULL DEFAULT '',
                UNIQUE(content)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                success INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_category
            ON memories(category)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_created
            ON conversations(created_at)
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # MEMORY.md 文件操作
    # ------------------------------------------------------------------

    def load_memory_file(self) -> str:
        """加载 MEMORY.md 文件内容。

        Returns:
            记忆内容文本，文件不存在时返回空字符串。
        """
        if not self.memory_file.exists():
            return ""

        try:
            content = self.memory_file.read_text(encoding="utf-8").strip()
            if len(content) > _MEMORY_MAX_CHARS:
                content = content[:_MEMORY_MAX_CHARS] + "\n...[记忆已截断]"
            return content
        except Exception as e:
            logger.warning("加载 MEMORY.md 失败: %s", e)
            return ""

    def save_memory_file(self, content: str) -> None:
        """写入 MEMORY.md 文件。

        Args:
            content: 要写入的内容。
        """
        try:
            self.memory_file.write_text(content, encoding="utf-8")
            logger.info("MEMORY.md 已更新 (%d 字符)", len(content))
        except Exception as e:
            logger.error("写入 MEMORY.md 失败: %s", e)

    def append_to_memory_file(self, line: str) -> None:
        """向 MEMORY.md 追加一行。

        Args:
            line: 要追加的文本行。
        """
        existing = ""
        if self.memory_file.exists():
            existing = self.memory_file.read_text(encoding="utf-8").rstrip("\n")
        self.save_memory_file(existing + "\n" + line + "\n")

    # ------------------------------------------------------------------
    # SQLite 记忆操作
    # ------------------------------------------------------------------

    def add_memory(self, content: str, category: str = "fact", source: str = "review", importance: float = 0.5) -> int:
        """添加一条记忆，自动去重（相同内容不重复写入）。

        Args:
            content: 记忆内容。
            category: 分类（fact/preference/experience/skill_reference）。
            source: 来源（user_input/review/manual）。
            importance: 重要性评分。

        Returns:
            新记录的 ID（重复内容返回 0）。
        """
        now = datetime.now().isoformat(timespec="seconds")
        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "INSERT INTO memories (content, category, source, importance, created_at) VALUES (?, ?, ?, ?, ?)",
                    (content, category, source, importance, now),
                )
                conn.commit()
                memory_id = cursor.lastrowid
                logger.info("新记忆 #%d [%s]: %s", memory_id, category, content[:80])

                # 同步到向量 RAG（如果可用），便于语义检索
                if self._rag_store is not None:
                    try:
                        _doc_id = f"mem_{hashlib.md5(content.encode()).hexdigest()[:12]}"
                        self._rag_store.ingest_document(_doc_id, content,
                                                        metadata={"category": category, "source": source})
                    except Exception as _ve:
                        logger.debug("记忆向量化失败（非致命）: %s", _ve)

                return memory_id or 0
            except sqlite3.IntegrityError:
                # UNIQUE 约束冲突 → 内容已存在，静默跳过
                return 0

    def search_memories(self, keywords: str, limit: int = 5) -> list[MemoryEntry]:
        """搜索记忆：优先向量语义检索，降级回关键词 LIKE 搜索。

        Args:
            keywords: 搜索关键词或自然语言查询。
            limit: 返回上限。

        Returns:
            匹配的记忆列表。
        """
        # 尝试向量检索（需要 rag_store 且有 memories collection）
        if self._rag_store is not None:
            try:
                results = self._rag_store.retrieve_context(keywords, top_k=limit)
                if results:
                    entries: list[MemoryEntry] = []
                    for r in results:
                        entries.append(MemoryEntry(
                            id=0,
                            content=r.get("text", ""),
                            category=r.get("metadata", {}).get("category", "fact"),
                            source=r.get("metadata", {}).get("source", "review"),
                            created_at="",
                            importance=max(0.0, min(1.0, 1.0 - r.get("distance", 0.5))),
                        ))
                    return entries
            except Exception as _ve:
                logger.debug("向量记忆检索失败，降级为 LIKE: %s", _ve)

        # 降级：SQLite LIKE 关键词搜索
        conn = self._connect()
        safe_keywords = (
            keywords.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            .replace("'", "''")
        )
        rows = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? ORDER BY importance DESC LIMIT ?",
            (f"%{safe_keywords}%", limit),
        ).fetchall()

        return [
            MemoryEntry(
                id=r["id"],
                content=r["content"],
                category=r["category"],
                source=r["source"],
                created_at=r["created_at"],
                importance=r["importance"],
            )
            for r in rows
        ]

    def get_recent_memories(self, limit: int = 10) -> list[MemoryEntry]:
        """获取最近的记忆条目。

        Args:
            limit: 返回上限。

        Returns:
            最近的记忆列表。
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            MemoryEntry(
                id=r["id"],
                content=r["content"],
                category=r["category"],
                source=r["source"],
                created_at=r["created_at"],
                importance=r["importance"],
            )
            for r in rows
        ]

    def get_memory_context(self, query: str = "") -> str:
        """构建注入到 Prompt 的记忆上下文。

        合并 MEMORY.md 和 SQLite 检索结果。

        Args:
            query: 当前用户查询（用于检索相关记忆）。

        Returns:
            格式化的记忆上下文文本。
        """
        parts: list[str] = []

        # 从 MEMORY.md 加载
        file_content = self.load_memory_file()
        if file_content:
            parts.append(f"[长期记忆]\n{file_content}")

        # 从 SQLite 检索相关记忆
        if query:
            memories = self.search_memories(query, limit=3)
            if memories:
                mem_lines = [f"- {m.content}" for m in memories]
                parts.append("[相关记忆]\n" + "\n".join(mem_lines))
        else:
            memories = self.get_recent_memories(limit=3)
            if memories:
                mem_lines = [f"- {m.content}" for m in memories]
                parts.append("[近期记忆]\n" + "\n".join(mem_lines))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 对话历史
    # ------------------------------------------------------------------

    def save_conversation(self, query: str, answer: str, success: bool = True) -> int:
        """保存一条对话记录。

        Args:
            query: 用户查询。
            answer: Agent 回答。
            success: 任务是否成功完成。

        Returns:
            新记录的 ID。
        """
        now = datetime.now().isoformat(timespec="seconds")
        with self._write_lock:
            conn = self._connect()
            cursor = conn.execute(
                "INSERT INTO conversations (query, answer, success, created_at) VALUES (?, ?, ?, ?)",
                (query, answer[:2000], int(success), now),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_recent_conversations(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近的对话记录。

        Args:
            limit: 返回上限。

        Returns:
            对话记录列表。
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "id": r["id"],
                "query": r["query"],
                "answer": r["answer"],
                "success": bool(r["success"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, int]:
        """获取记忆系统统计信息。

        Returns:
            包含 memories_count 和 conversations_count 的字典。
        """
        conn = self._connect()
        mem_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        return {"memories_count": mem_count, "conversations_count": conv_count}

    def close(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            conn.close()
            self._local.conn = None
