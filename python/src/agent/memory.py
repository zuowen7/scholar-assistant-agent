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
from datetime import datetime, timezone
from time import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_MAX_CHARS = 3000
_MEMORY_MAX_ROWS = 500
_MEMORY_PRUNE_IMPORTANCE = 0.3
_MEMORY_FUZZY_DUP_THRESHOLD = 0.6

# Time-decay settings (borrowed from AutoResearchClaw decay.py)
_DECAY_HALF_LIFE_DAYS = 90.0
_DECAY_MAX_AGE_DAYS = 365.0

SCHOLAR_ASSISTANT_DEFAULT_MEMORY = """# Scholar Assistant Project Memory

## Product North Star

- Scholar Assistant is "Codex for papers": a privacy-first academic workspace where the agent reads and edits the user's PDFs, drafts, bibliographies, data, and export artifacts directly inside the selected workspace.
- Prefer concrete work on the current file/workspace over generic academic writing advice.

## Hard Invariants

- Keep frontend and backend SSE contracts in sync. Translation events are prefixed `translate.*`; Agent events follow `agent/models.py`.
- Agent tool metadata key is `tool_name` across `tool_call`, `tool_result`, and `await_approval`.
- Ledger/companion routes use `?doc_id=` query params because `doc_id` may be a full file path containing `/`.
- Pure document Q&A must use the oneshot document QA path and must not enter ReAct or write files.
- Explicit file mutation or command execution goes through Agent ReAct and workspace boundary approval.
- Out-of-workspace file access must trigger approval; never silently bypass `WorkspaceEnv.resolve()` or `SecurityGate`.
- Monaco open tabs reload after Agent `write_file` / `str_replace`, but tabs with unsaved user edits must not be overwritten.

## Repeated Failure Lessons

- AI panel preset actions such as polish, expand, review, and translate should call `/api/edit` once, not `/api/agent/v2/chat`.
- Translation section/context markers belong in system prompt context or sanitizer rules; never prepend them as user text that can be translated into output.
- Preserve paragraph/block alignment during translation. If the model returns extra paragraphs, merge or distribute rather than dropping positions.
- Runtime config roles differ: root `config/default.yaml` is shipped default; `python/config/default.yaml` is runtime copy; `python/config/default.local.yaml` is user override.
- Windows proxy variables can make `httpx` hang on import; `start_dev.bat` and Tauri subprocess launch should clear proxy env vars.
"""


# ---------------------------------------------------------------------------
# Time-decay weighting (borrowed from AutoResearchClaw memory/decay.py)
# ---------------------------------------------------------------------------

def _time_decay_weight(created_at: str, half_life_days: float = _DECAY_HALF_LIFE_DAYS,
                       max_age_days: float = _DECAY_MAX_AGE_DAYS) -> float:
    """Exponential decay weight: 1.0 for fresh, 0.0 for older than max_age_days."""
    import math
    try:
        ts = datetime.fromisoformat(created_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 1.0
    age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
    if age_days < 0:
        return 1.0
    if age_days > max_age_days:
        return 0.0
    return math.exp(-age_days * math.log(2) / half_life_days)


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

    def __init__(
        self,
        data_dir: str | Path = "data/agent",
        rag_store: Any | None = None,
        default_memory: str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.data_dir / "MEMORY.md"
        self._db_path = self.data_dir / "memory.db"
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._rag_store = rag_store  # 可选向量搜索后端（RAGStore，使用独立 collection）
        self._init_db()
        self._seed_default_memory(default_memory)

    def _seed_default_memory(self, default_memory: str | None) -> None:
        """Create MEMORY.md from a project default without overwriting user memory."""
        if not default_memory or self.memory_file.exists():
            return
        content = default_memory.strip()
        if not content:
            return
        try:
            self.memory_file.write_text(content + "\n", encoding="utf-8")
            logger.info("MEMORY.md seeded from project default (%d chars)", len(content))
        except Exception as e:
            logger.warning("默认 MEMORY.md 初始化失败: %s", e)

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
        """添加一条记忆，自动去重（精确+模糊）。

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
                # Fuzzy dedup: only for review-sourced experience (the noisy category)
                if source == "review" and category == "experience":
                    if self._is_fuzzy_duplicate(conn, content):
                        return 0

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

                # Auto-prune if exceeding max rows
                self._auto_prune(conn)

                return memory_id or 0
            except sqlite3.IntegrityError:
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

        # 降级：SQLite LIKE 关键词搜索 + 时间衰减排序
        conn = self._connect()
        safe_keywords = (
            keywords.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            .replace("'", "''")
        )
        rows = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ?",
            (f"%{safe_keywords}%",),
        ).fetchall()

        # Score = importance * time_decay; drop entries with negligible effective score
        scored: list[tuple[float, MemoryEntry]] = []
        for r in rows:
            decay = _time_decay_weight(r["created_at"])
            effective = float(r["importance"]) * decay
            if effective < 0.05:
                continue
            entry = MemoryEntry(
                id=r["id"],
                content=r["content"],
                category=r["category"],
                source=r["source"],
                created_at=r["created_at"],
                importance=r["importance"],
            )
            scored.append((effective, entry))
        scored.sort(key=lambda x: x[0], reverse=True)

        return [entry for _, entry in scored[:limit]]

    def update_confidence(self, memory_id: int, delta: float) -> bool:
        """Adjust a memory's importance by delta, clamped to [0.0, 1.0].

        Positive delta = success reinforcement; negative = failure demotion.
        """
        with self._write_lock:
            conn = self._connect()
            row = conn.execute("SELECT importance FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row is None:
                return False
            new_val = max(0.0, min(1.0, float(row["importance"]) + delta))
            conn.execute("UPDATE memories SET importance = ? WHERE id = ?", (new_val, memory_id))
            conn.commit()
            return True

    def _get_by_id(self, memory_id: int) -> dict | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return dict(row) if row else None

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

    # ------------------------------------------------------------------
    # 去重 & 修剪
    # ------------------------------------------------------------------

    @staticmethod
    def _char_ngrams(text: str, n: int = 2) -> set[str]:
        """生成字符 n-gram 集合用于模糊匹配。Bigram (n=2) works well for CJK."""
        text = text.lower().strip()
        if len(text) < n:
            return {text}
        return {text[i:i + n] for i in range(len(text) - n + 1)}

    @staticmethod
    def _jaccard(set_a: set[str], set_b: set[str]) -> float:
        """计算两个集合的 Jaccard 相似度。"""
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def _is_fuzzy_duplicate(self, conn: sqlite3.Connection, content: str) -> bool:
        """检查新内容是否与已有记忆高度相似（模糊去重）。"""
        # Skip fuzzy check for very short content
        if len(content) < 10:
            return False

        new_ngrams = self._char_ngrams(content)

        # Only check recent memories in same category (limit scan for performance)
        rows = conn.execute(
            "SELECT content FROM memories ORDER BY id DESC LIMIT 50"
        ).fetchall()

        for (existing,) in rows:
            if len(existing) < 10:
                continue
            existing_ngrams = self._char_ngrams(existing)
            sim = self._jaccard(new_ngrams, existing_ngrams)
            if sim >= _MEMORY_FUZZY_DUP_THRESHOLD:
                logger.debug("模糊去重: 新内容与已有记忆相似度 %.2f，跳过", sim)
                return True
        return False

    def _auto_prune(self, conn: sqlite3.Connection) -> None:
        """当记忆条数超过上限时，归档低重要性旧记忆到 JSONL 文件后再删除。"""
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        if count <= _MEMORY_MAX_ROWS:
            return

        to_delete = count - _MEMORY_MAX_ROWS + 50  # extra buffer to avoid frequent pruning
        rows = conn.execute(
            "SELECT id, content, category, source, importance, created_at "
            "FROM memories WHERE importance <= ? ORDER BY id ASC LIMIT ?",
            (_MEMORY_PRUNE_IMPORTANCE, to_delete),
        ).fetchall()
        if not rows:
            return

        # Archive to JSONL before deleting so entries can be recovered
        archive_path = self.data_dir / "memory_archive.jsonl"
        archived_at = datetime.now().isoformat(timespec="seconds")
        try:
            with open(archive_path, "a", encoding="utf-8") as f:
                for row in rows:
                    entry = {
                        "id": row["id"],
                        "content": row["content"],
                        "category": row["category"],
                        "source": row["source"],
                        "importance": row["importance"],
                        "created_at": row["created_at"],
                        "archived_at": archived_at,
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("记忆归档写入失败（非致命）: %s", exc)

        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        logger.info("记忆修剪+归档: %d → %d 条 (归档 %d 条到 memory_archive.jsonl)", count, remaining, len(ids))

    def close(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception as e:
                logger.debug("wal checkpoint failed: %s", e)
            conn.close()
            self._local.conn = None
