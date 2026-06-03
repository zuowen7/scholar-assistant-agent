"""原子 JSON 写工具。

写入过程：先写临时文件 → fsync → os.replace（原子重命名），
配合路径级 threading.Lock 防止并发写互相覆盖。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_locks: dict[Path, threading.Lock] = {}
_locks_meta = threading.Lock()


def _file_lock(path: Path) -> threading.Lock:
    with _locks_meta:
        if path not in _locks:
            _locks[path] = threading.Lock()
        return _locks[path]


def atomic_write_json(path: Path, data: Any) -> None:
    """将 data 原子写入 path（JSON 格式）。

    使用 tmpfile + os.replace 保证写入中途崩溃不会损坏原文件；
    路径级 Lock 防止并发写互相覆盖。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _file_lock(path)
    with lock:
        tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except Exception as e:
            logger.debug("atomic_write_json failed, cleaning up temp file: %s", e)
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
