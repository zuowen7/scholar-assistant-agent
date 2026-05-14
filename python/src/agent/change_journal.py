"""变更日志与备份管理 — 每次 destructive 操作产生一个 patch 条目。

目录结构:
    <workspace.root>/.agent_backup/
    ├── journal.jsonl                 # 全部操作的时间线（追加写）
    ├── 20260426_103022_a1b2/         # 每次 destructive 操作一个目录
    │   ├── meta.json                 # {tool, args, file, original_sha256}
    │   └── files/
    │       └── src/agent/agent.py.bak
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChangeJournal:
    """管理 Agent 工作区的变更日志和文件备份。

    所有 destructive 操作（str_replace, write_file 覆盖等）必须经过本类：
    1. 创建备份 ID 和目录
    2. 备份原始文件
    3. 写入 journal 条目
    4. 提供 undo 能力
    """

    def __init__(self, backup_root: Path):
        self._root = backup_root
        self._journal_path = backup_root / "journal.jsonl"
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def journal_path(self) -> Path:
        return self._journal_path

    def generate_backup_id(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short = uuid.uuid4().hex[:4]
        return f"{ts}_{short}"

    def backup_file(self, backup_id: str, file_path: Path, workspace_root: Path) -> str:
        """将文件备份到 .agent_backup/<backup_id>/files/<rel>.bak。

        Args:
            backup_id: 备份标识符。
            file_path: 要备份的文件绝对路径。
            workspace_root: 工作区根目录（用于计算相对路径）。

        Returns:
            备份文件的绝对路径。
        """
        try:
            rel = file_path.relative_to(workspace_root)
        except ValueError:
            rel = Path(file_path.name)

        backup_dir = self._root / backup_id / "files"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / rel
        backup_file.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(str(file_path), str(backup_file))

        # 写 meta.json
        meta_path = self._root / backup_id / "meta.json"
        meta = {
            "backup_id": backup_id,
            "original_path": str(rel).replace("\\", "/"),
            "original_sha256": _sha256(file_path),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                existing.update(meta)
                meta = existing
        from src.utils.atomic_io import atomic_write_json
        atomic_write_json(meta_path, meta)

        return str(backup_file)

    def append_entry(
        self,
        *,
        backup_id: str,
        session_id: str,
        event_id: str,
        tool: str,
        file: str,
        operation: str,
        original_sha256: str = "",
        new_sha256: str = "",
        diff_preview: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict:
        """追加一条 journal 记录。"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event_id": event_id,
            "backup_id": backup_id,
            "tool": tool,
            "file": file,
            "operation": operation,
            "original_sha256": original_sha256,
            "new_sha256": new_sha256,
            "diff_preview": diff_preview[:500],  # 截断防止 journal 膨胀
            "undone_at": None,
        }
        if extra:
            entry.update(extra)

        with open(self._journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry

    def read_entries(self) -> list[dict]:
        """读取所有 journal 条目（从旧到新）。"""
        if not self._journal_path.exists():
            return []
        entries = []
        with open(self._journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def undo(self, count: int = 1, backup_id: str | None = None) -> list[dict]:
        """回退最近 N 次操作（或指定 backup_id）。

        Args:
            count: 回退次数。
            backup_id: 指定回退到某个 backup 点（与 count 互斥）。

        Returns:
            被回退的条目列表。
        """
        entries = self.read_entries()

        # 找到未 undone 的条目
        undoneable = [e for e in entries if e.get("undone_at") is None]
        undoneable.reverse()

        targets: list[dict] = []
        if backup_id:
            targets = [e for e in undoneable if e.get("backup_id") == backup_id]
        else:
            targets = undoneable[:count]

        reverted = []
        for entry in targets:
            backup_id_val = entry.get("backup_id", "")
            rel_path = entry.get("file", "")
            backup_file = self._root / backup_id_val / "files" / rel_path

            if backup_file.exists():
                workspace_root = self._root.parent  # .agent_backup 的父目录就是 workspace root
                target = workspace_root / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_file), str(target))

            entry["undone_at"] = datetime.now(timezone.utc).isoformat()
            reverted.append(entry)

        # 重写整个 journal（更新 undone_at）
        self._rewrite_journal(entries)

        return reverted

    def _rewrite_journal(self, entries: list[dict]) -> None:
        """重写 journal 文件（undo 操作后更新状态）。"""
        with open(self._journal_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _sha256(path: Path) -> str:
    """计算文件的 SHA-256 哈希。"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return ""
