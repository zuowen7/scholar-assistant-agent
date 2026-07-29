"""Session — JSONL 会话持久化 + resume + rotate。

参考 claw-code runtime/session.rs:
  - JSONL 格式（每行一条消息）
  - 256KB rotate，最多 3 个 rotate 文件
  - 单字段 16KB 截断
  - resume 从文件恢复
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
import zlib
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agent_v2.runtime.file_mutations import (
    atomic_write_bytes,
    atomic_write_text,
    read_text_exact,
    text_hash,
)
from src.agent_v2.types import (
    ContentBlock,
    Message,
    MessageRole,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolResultBlock,
    ToolUseBlock,
)

_SESSION_VERSION = 2
_ROTATE_AFTER_BYTES = 256 * 1024
_MAX_ROTATED_FILES = 3
_MAX_FIELD_CHARS = 16 * 1024
_TRUNCATION_MARKER = "… [truncated]"
_SESSION_IO_LOCKS = tuple(threading.RLock() for _ in range(64))
_TRANSIENT_REPLACE_ERRNOS = frozenset({13, 16})
_TRANSIENT_REPLACE_WINERRORS = frozenset({5, 32, 33})
_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4)


def _session_io_lock(path: str | Path) -> threading.RLock:
    normalized = os.path.normcase(os.path.abspath(os.fspath(path)))
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=2).digest()
    index = int.from_bytes(digest, "big") % len(_SESSION_IO_LOCKS)
    return _SESSION_IO_LOCKS[index]


def _replace_with_retry(source: str | Path, target: str | Path) -> None:
    for attempt in range(len(_REPLACE_RETRY_DELAYS) + 1):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            transient = (
                exc.errno in _TRANSIENT_REPLACE_ERRNOS
                or getattr(exc, "winerror", None) in _TRANSIENT_REPLACE_WINERRORS
            )
            if not transient or attempt >= len(_REPLACE_RETRY_DELAYS):
                raise
            time.sleep(_REPLACE_RETRY_DELAYS[attempt])


@dataclass
class SessionMeta:
    session_id: str = ""
    version: int = _SESSION_VERSION
    workspace: str = ""
    model: str = ""
    created_ms: int = 0
    updated_ms: int = 0
    total_usage: TokenUsage = field(default_factory=TokenUsage)
    state: str = "IDLE"
    outcome: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionFork:
    parent_session_id: str
    branch_name: str | None = None


@dataclass
class MutationRecord:
    mutation_id: str
    turn_id: str
    tool_use_id: str
    path: str
    before_exists: bool
    before_content: str
    before_hash: str
    after_hash: str
    created_ms: int
    undone: bool = False
    is_binary: bool = False
    operation_key: str = ""


class MutationConflictError(RuntimeError):
    """Undo refused because a file changed after the recorded mutation."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _truncate(s: str, max_chars: int = _MAX_FIELD_CHARS) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + _TRUNCATION_MARKER


def _block_to_dict(block: ContentBlock) -> dict[str, Any]:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": _truncate(block.text)}
    if isinstance(block, ThinkingBlock):
        return {
            "type": "thinking",
            "thinking": _truncate(block.thinking),
            "signature": block.signature,
        }
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": _truncate(block.input),
        }
    if isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "tool_name": block.tool_name,
            "output": _truncate(block.output),
            "is_error": block.is_error,
            "status": block.status,
            "truncated": block.truncated,
            "original_chars": block.original_chars,
            "returned_chars": block.returned_chars,
            "metadata": block.metadata,
        }
    return {"type": "unknown"}


def _dict_to_block(d: dict[str, Any]) -> ContentBlock:
    t = d.get("type", "")
    if t == "text":
        return TextBlock(text=d.get("text", ""))
    if t == "thinking":
        return ThinkingBlock(thinking=d.get("thinking", ""), signature=d.get("signature"))
    if t == "tool_use":
        return ToolUseBlock(id=d.get("id", ""), name=d.get("name", ""), input=d.get("input", "{}"))
    if t == "tool_result":
        return ToolResultBlock(
            tool_use_id=d.get("tool_use_id", ""),
            tool_name=d.get("tool_name", ""),
            output=d.get("output", ""),
            is_error=d.get("is_error", False),
            status=d.get("status", ""),
            truncated=d.get("truncated", False),
            original_chars=d.get("original_chars", 0),
            returned_chars=d.get("returned_chars", 0),
            metadata=d.get("metadata", {}) if isinstance(d.get("metadata", {}), dict) else {},
        )
    return TextBlock(text=str(d))


def _message_to_dict(msg: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": msg.role.value, "blocks": [_block_to_dict(b) for b in msg.blocks]}
    if msg.usage:
        d["usage"] = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
    return d


def _dict_to_message(d: dict[str, Any]) -> Message:
    blocks = [_dict_to_block(b) for b in d.get("blocks", [])]
    usage = None
    if "usage" in d:
        u = d["usage"]
        usage = TokenUsage(
            input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0)
        )
    return Message(role=MessageRole(d.get("role", "user")), blocks=blocks, usage=usage)


def _mutation_to_dict(record: MutationRecord) -> dict[str, Any]:
    compressed = zlib.compress(record.before_content.encode("utf-8"), level=6)
    return {
        "record_type": "mutation",
        "mutation_id": record.mutation_id,
        "turn_id": record.turn_id,
        "tool_use_id": record.tool_use_id,
        "path": record.path,
        "before_exists": record.before_exists,
        "before_content_zlib_b64": base64.b64encode(compressed).decode("ascii"),
        "before_hash": record.before_hash,
        "after_hash": record.after_hash,
        "created_ms": record.created_ms,
        "undone": record.undone,
        "is_binary": record.is_binary,
        "operation_key": record.operation_key,
    }


def _dict_to_mutation(data: dict[str, Any]) -> MutationRecord:
    encoded = str(data.get("before_content_zlib_b64", ""))
    before_content = ""
    if encoded:
        before_content = zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
    return MutationRecord(
        mutation_id=str(data.get("mutation_id", "")),
        turn_id=str(data.get("turn_id", "")),
        tool_use_id=str(data.get("tool_use_id", "")),
        path=str(data.get("path", "")),
        before_exists=bool(data.get("before_exists", False)),
        before_content=before_content,
        before_hash=str(data.get("before_hash", "")),
        after_hash=str(data.get("after_hash", "")),
        created_ms=int(data.get("created_ms", 0)),
        undone=bool(data.get("undone", False)),
        is_binary=bool(data.get("is_binary", False)),
        operation_key=str(data.get("operation_key", "")),
    )


class Session:
    """JSONL 会话持久化。

    Usage:
        session = Session(workspace="/path/to/ws", model="claude-opus-4-6")
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="hello")]))
        session.save("/path/to/session.jsonl")

        # Resume
        session2 = Session.load("/path/to/session.jsonl")
    """

    def __init__(self, workspace: str = "", model: str = "", session_id: str = ""):
        self.meta = SessionMeta(
            session_id=session_id or uuid.uuid4().hex[:12],
            version=_SESSION_VERSION,
            workspace=workspace,
            model=model,
            created_ms=_now_ms(),
            updated_ms=_now_ms(),
        )
        self._messages: list[Message] = []
        self._mutations: list[MutationRecord] = []
        self._save_path: str = ""  # set by router for auto-save
        self.fork_meta: SessionFork | None = None

    @property
    def session_id(self) -> str:
        return self.meta.session_id

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    def append(self, msg: Message) -> None:
        self._messages.append(msg)
        self.meta.updated_ms = _now_ms()
        if msg.usage:
            self.meta.total_usage = self.meta.total_usage + msg.usage

    def fork(self, branch_name: str | None = None) -> Session:
        """Create a new session forked from the current state."""
        now = _now_ms()
        forked = Session.__new__(Session)
        forked.meta = SessionMeta(
            session_id=uuid.uuid4().hex[:12],
            version=self.meta.version,
            workspace=self.meta.workspace,
            model=self.meta.model,
            created_ms=now,
            updated_ms=now,
            state=self.meta.state,
            outcome=dict(self.meta.outcome),
        )
        forked._messages = list(self._messages)
        forked._mutations = list(self._mutations)
        forked._save_path = ""
        forked.fork_meta = SessionFork(
            parent_session_id=self.session_id,
            branch_name=branch_name,
        )
        return forked

    def total_tokens(self) -> int:
        return self.meta.total_usage.total()

    def set_outcome(self, state: str, outcome: dict[str, Any] | None = None) -> None:
        self.meta.state = state
        self.meta.outcome = dict(outcome or {})
        self.meta.updated_ms = _now_ms()

    @property
    def mutation_journal(self) -> list[MutationRecord]:
        return list(self._mutations)

    def record_mutation(
        self,
        *,
        turn_id: str,
        tool_use_id: str,
        path: str | Path,
        before_exists: bool,
        before_content: str,
        after_content: str,
        operation_key: str = "",
    ) -> MutationRecord:
        record = MutationRecord(
            mutation_id=uuid.uuid4().hex,
            turn_id=turn_id,
            tool_use_id=tool_use_id,
            path=str(Path(path).resolve()),
            before_exists=before_exists,
            before_content=before_content,
            before_hash=text_hash(before_content) if before_exists else "",
            after_hash=text_hash(after_content),
            created_ms=_now_ms(),
            operation_key=operation_key,
        )
        self._mutations.append(record)
        self.meta.updated_ms = _now_ms()
        return record

    def record_binary_mutation(
        self,
        *,
        turn_id: str,
        tool_use_id: str,
        path: str | Path,
        before_exists: bool,
        before_content: bytes,
        after_content: bytes,
        operation_key: str = "",
    ) -> MutationRecord:
        record = MutationRecord(
            mutation_id=uuid.uuid4().hex,
            turn_id=turn_id,
            tool_use_id=tool_use_id,
            path=str(Path(path).resolve()),
            before_exists=before_exists,
            before_content=base64.b64encode(before_content).decode("ascii"),
            before_hash=(hashlib.sha256(before_content).hexdigest() if before_exists else ""),
            after_hash=hashlib.sha256(after_content).hexdigest(),
            created_ms=_now_ms(),
            is_binary=True,
            operation_key=operation_key,
        )
        self._mutations.append(record)
        self.meta.updated_ms = _now_ms()
        return record

    def applied_mutation(self, operation_key: str) -> MutationRecord | None:
        if not operation_key:
            return None
        for record in reversed(self._mutations):
            if record.operation_key == operation_key and not record.undone:
                path = Path(record.path)
                if not path.is_file():
                    return None
                current_hash = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if record.is_binary
                    else text_hash(read_text_exact(path))
                )
                return record if current_hash == record.after_hash else None
        return None

    def undo_last_turn(self) -> list[str]:
        pending = [record for record in self._mutations if not record.undone]
        if not pending:
            raise LookupError("No recorded Agent mutation is available to undo")
        turn_id = pending[-1].turn_id
        records = [record for record in pending if record.turn_id == turn_id]
        workspace = Path(self.meta.workspace).resolve()

        # Validate each file once against the last mutation in the turn before
        # touching any file. This prevents overwriting later user edits.
        latest_by_path: dict[str, MutationRecord] = {}
        for record in records:
            latest_by_path[record.path] = record
        for path_str, record in latest_by_path.items():
            path = Path(path_str).resolve()
            try:
                path.relative_to(workspace)
            except ValueError as exc:
                raise MutationConflictError(
                    f"Recorded mutation is outside the session workspace: {path}"
                ) from exc
            if not path.is_file():
                raise MutationConflictError(f"Cannot undo because the file is missing: {path}")
            current_hash = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if record.is_binary
                else text_hash(read_text_exact(path))
            )
            if current_hash != record.after_hash:
                raise MutationConflictError(
                    f"Cannot undo because the file changed after the Agent edit: {path}"
                )

        restored_paths: list[str] = []
        for record in reversed(records):
            path = Path(record.path).resolve()
            if path.is_file():
                current_hash = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if record.is_binary
                    else text_hash(read_text_exact(path))
                )
            else:
                current_hash = ""
            if current_hash != record.after_hash:
                raise MutationConflictError(
                    f"Cannot undo because the mutation chain diverged: {path}"
                )
            if record.before_exists:
                if record.is_binary:
                    atomic_write_bytes(path, base64.b64decode(record.before_content))
                else:
                    atomic_write_text(path, record.before_content)
            else:
                path.unlink()
            record.undone = True
            restored_paths.append(str(path))

        self.meta.updated_ms = _now_ms()
        self.meta.outcome = {
            **self.meta.outcome,
            "last_undo": {
                "turn_id": turn_id,
                "files": sorted(set(restored_paths)),
                "mutation_count": len(records),
            },
        }
        return sorted(set(restored_paths))

    def save(self, path: str | Path) -> None:
        p = Path(path)
        with _session_io_lock(p):
            p.parent.mkdir(parents=True, exist_ok=True)
            meta_dict = {
                "version": self.meta.version,
                "session_id": self.meta.session_id,
                "workspace": self.meta.workspace,
                "model": self.meta.model,
                "created_ms": self.meta.created_ms,
                "updated_ms": self.meta.updated_ms,
                "state": self.meta.state,
                "outcome": self.meta.outcome,
                "total_usage": {
                    "input_tokens": self.meta.total_usage.input_tokens,
                    "output_tokens": self.meta.total_usage.output_tokens,
                },
            }
            if self.fork_meta:
                meta_dict["fork"] = {
                    "parent_session_id": self.fork_meta.parent_session_id,
                    "branch_name": self.fork_meta.branch_name,
                }
            fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(meta_dict, ensure_ascii=False) + "\n")
                    for msg in self._messages:
                        f.write(json.dumps(_message_to_dict(msg), ensure_ascii=False) + "\n")
                    for record in self._mutations:
                        f.write(json.dumps(_mutation_to_dict(record), ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                _replace_with_retry(tmp_name, p)
            except Exception:
                with suppress(OSError):
                    os.unlink(tmp_name)
                raise

    @staticmethod
    def load(path: str | Path) -> Session:
        p = Path(path)
        with _session_io_lock(p):
            if not p.is_file():
                return Session()
            messages: list[Message] = []
            mutations: list[MutationRecord] = []
            meta_data: dict[str, Any] = {}
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "session_id" in d:
                        meta_data = d
                        continue
                    if "role" in d:
                        messages.append(_dict_to_message(d))
                        continue
                    if d.get("record_type") == "mutation":
                        try:
                            mutations.append(_dict_to_mutation(d))
                        except Exception:
                            continue
        session = Session(
            workspace=meta_data.get("workspace", ""),
            model=meta_data.get("model", ""),
            session_id=meta_data.get("session_id", ""),
        )
        if meta_data:
            session.meta.created_ms = meta_data.get("created_ms", 0)
            session.meta.updated_ms = meta_data.get("updated_ms", 0)
            persisted_state = meta_data.get("state", "IDLE")
            outcome = meta_data.get("outcome", {})
            persisted_outcome = outcome if isinstance(outcome, dict) else {}
            if persisted_state in {"RUNNING", "DRAINING", "FINALIZING"}:
                session.meta.state = "PARTIAL"
                session.meta.outcome = {
                    **persisted_outcome,
                    "stop_code": "process_interrupted",
                    "stop_reason": "Runtime stopped before a terminal state was persisted",
                    "interrupted_state": persisted_state,
                }
            else:
                session.meta.state = persisted_state
                session.meta.outcome = persisted_outcome
            tu = meta_data.get("total_usage", {})
            session.meta.total_usage = TokenUsage(
                input_tokens=tu.get("input_tokens", 0), output_tokens=tu.get("output_tokens", 0)
            )
            fork_data = meta_data.get("fork")
            if fork_data and isinstance(fork_data, dict):
                session.fork_meta = SessionFork(
                    parent_session_id=fork_data.get("parent_session_id", ""),
                    branch_name=fork_data.get("branch_name"),
                )
        session._messages = messages
        session._mutations = mutations
        session._save_path = str(p)
        return session

    def should_rotate(self, path: str | Path) -> bool:
        p = Path(path)
        if not p.is_file():
            return False
        return p.stat().st_size >= _ROTATE_AFTER_BYTES

    def rotate(self, path: str | Path) -> Path:
        p = Path(path)
        with _session_io_lock(p):
            rotated = Path(str(p) + ".1")
            # Shift existing rotated files with replace semantics so readers
            # never observe a partially moved chain.
            for i in range(_MAX_ROTATED_FILES - 1, 0, -1):
                src = Path(str(p) + f".{i}")
                dst = Path(str(p) + f".{i + 1}")
                if src.is_file():
                    _replace_with_retry(src, dst)
            if p.is_file():
                _replace_with_retry(p, rotated)
            return rotated

    def save_with_rotate(self, path: str | Path) -> None:
        with _session_io_lock(path):
            if self.should_rotate(path):
                self.rotate(path)
            self.save(path)

    @property
    def message_count(self) -> int:
        return len(self._messages)
