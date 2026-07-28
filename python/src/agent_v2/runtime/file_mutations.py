"""Crash-safe text-file mutation primitives shared by tools and Undo."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path


def text_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def read_text_exact(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def atomic_write_text(path: Path, content: str) -> None:
    """Replace *path* only after a same-directory temp file is durable.

    A temp file in the target directory keeps ``os.replace`` on one filesystem.
    The original remains intact if writing or fsync fails.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode: int | None = None
    if path.exists():
        original_mode = stat.S_IMODE(path.stat().st_mode)

    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".agent-tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if original_mode is not None:
            os.chmod(temp_name, original_mode)
        os.replace(temp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(temp_name)
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode: int | None = None
    if path.exists():
        original_mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".agent-tmp",
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if original_mode is not None:
            os.chmod(temp_name, original_mode)
        os.replace(temp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(temp_name)
        raise
