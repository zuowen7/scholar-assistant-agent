"""Session — JSONL 会话持久化 + resume + rotate。

参考 claw-code runtime/session.rs:
  - JSONL 格式（每行一条消息）
  - 256KB rotate，最多 3 个 rotate 文件
  - 单字段 16KB 截断
  - resume 从文件恢复
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

_SESSION_VERSION = 1
_ROTATE_AFTER_BYTES = 256 * 1024
_MAX_ROTATED_FILES = 3
_MAX_FIELD_CHARS = 16 * 1024
_TRUNCATION_MARKER = "… [truncated]"


@dataclass
class SessionMeta:
    session_id: str = ""
    version: int = _SESSION_VERSION
    workspace: str = ""
    model: str = ""
    created_ms: int = 0
    updated_ms: int = 0
    total_usage: TokenUsage = field(default_factory=TokenUsage)


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
        return {"type": "thinking", "thinking": _truncate(block.thinking), "signature": block.signature}
    if isinstance(block, ToolUseBlock):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": _truncate(block.input)}
    if isinstance(block, ToolResultBlock):
        return {"type": "tool_result", "tool_use_id": block.tool_use_id, "tool_name": block.tool_name,
                "output": _truncate(block.output), "is_error": block.is_error}
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
            tool_use_id=d.get("tool_use_id", ""), tool_name=d.get("tool_name", ""),
            output=d.get("output", ""), is_error=d.get("is_error", False),
        )
    return TextBlock(text=str(d))


def _message_to_dict(msg: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": msg.role.value, "blocks": [_block_to_dict(b) for b in msg.blocks]}
    if msg.usage:
        d["usage"] = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    return d


def _dict_to_message(d: dict[str, Any]) -> Message:
    blocks = [_dict_to_block(b) for b in d.get("blocks", [])]
    usage = None
    if "usage" in d:
        u = d["usage"]
        usage = TokenUsage(input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0))
    return Message(role=MessageRole(d.get("role", "user")), blocks=blocks, usage=usage)


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
        self._save_path: str = ""  # set by router for auto-save

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

    def total_tokens(self) -> int:
        return self.meta.total_usage.total()

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"version": self.meta.version, "session_id": self.meta.session_id,
                                "workspace": self.meta.workspace, "model": self.meta.model,
                                "created_ms": self.meta.created_ms, "updated_ms": self.meta.updated_ms,
                                "total_usage": {"input_tokens": self.meta.total_usage.input_tokens,
                                                "output_tokens": self.meta.total_usage.output_tokens}},
                               ensure_ascii=False) + "\n")
            for msg in self._messages:
                f.write(json.dumps(_message_to_dict(msg), ensure_ascii=False) + "\n")

    @staticmethod
    def load(path: str | Path) -> Session:
        p = Path(path)
        if not p.is_file():
            return Session()
        messages: list[Message] = []
        meta_data: dict[str, Any] = {}
        with open(p, "r", encoding="utf-8") as f:
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
        session = Session(workspace=meta_data.get("workspace", ""), model=meta_data.get("model", ""),
                          session_id=meta_data.get("session_id", ""))
        if meta_data:
            session.meta.created_ms = meta_data.get("created_ms", 0)
            session.meta.updated_ms = meta_data.get("updated_ms", 0)
            tu = meta_data.get("total_usage", {})
            session.meta.total_usage = TokenUsage(input_tokens=tu.get("input_tokens", 0),
                                                   output_tokens=tu.get("output_tokens", 0))
        session._messages = messages
        return session

    def should_rotate(self, path: str | Path) -> bool:
        p = Path(path)
        if not p.is_file():
            return False
        return p.stat().st_size >= _ROTATE_AFTER_BYTES

    def rotate(self, path: str | Path) -> Path:
        p = Path(path)
        rotated = Path(str(p) + ".1")
        # Shift existing rotated files
        for i in range(_MAX_ROTATED_FILES - 1, 0, -1):
            src = Path(str(p) + f".{i}")
            dst = Path(str(p) + f".{i + 1}")
            if src.is_file():
                if dst.is_file():
                    dst.unlink()
                src.rename(dst)
        if p.is_file():
            if rotated.is_file():
                rotated.unlink()
            p.rename(rotated)
        return rotated

    def save_with_rotate(self, path: str | Path) -> None:
        if self.should_rotate(path):
            self.rotate(path)
        self.save(path)

    @property
    def message_count(self) -> int:
        return len(self._messages)
