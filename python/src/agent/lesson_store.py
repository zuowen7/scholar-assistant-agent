"""Session lesson extraction and prompt overlay.

Borrowed from AutoResearchClaw's evolution.py pattern: after each Agent
session, extract structured lessons from tool failures and loop warnings,
persist them in JSONL, and inject the most relevant ones into the next
session's system prompt as overlay text.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HALF_LIFE_DAYS = 30.0
_MAX_AGE_DAYS = 90.0


class LessonStore:
    """JSONL-backed store for Agent session lessons."""

    def __init__(self, data_dir: str) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "lessons.jsonl"

    def record(
        self,
        tool: str,
        category: str = "pipeline",
        severity: str = "warning",
        description: str = "",
        timestamp: str | None = None,
    ) -> None:
        entry = {
            "tool": tool,
            "category": category,
            "severity": severity,
            "description": description,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
        return entries

    def _time_weight(self, ts_iso: str) -> float:
        import math
        try:
            ts = datetime.fromisoformat(ts_iso)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
        except (ValueError, TypeError):
            return 0.0
        if age_days < 0:
            return 1.0
        if age_days > _MAX_AGE_DAYS:
            return 0.0
        return math.exp(-age_days * math.log(2) / _HALF_LIFE_DAYS)

    def build_overlay(self, tool_name: str, max_lessons: int = 5) -> str:
        entries = self.load_all()
        scored: list[tuple[float, dict]] = []
        for e in entries:
            w = self._time_weight(e.get("timestamp", ""))
            if w <= 0.0:
                continue
            if e.get("tool") == tool_name:
                w *= 2.0
            if e.get("severity") == "error":
                w *= 1.5
            scored.append((w, e))
        scored.sort(key=lambda x: x[0], reverse=True)

        top = scored[:max_lessons]
        if not top:
            return ""

        lines = ["[过往经验教训 — 避免重复犯错]"]
        severity_icon = {"error": "x", "warning": "!", "info": "i"}
        for i, (_, e) in enumerate(top, 1):
            icon = severity_icon.get(e.get("severity", ""), "-")
            lines.append(f"  {i}. [{icon}] {e.get('tool', '?')}: {e.get('description', '')}")
        lines.append("请吸取以上教训，避免重复相同错误。")
        return "\n".join(lines)


def extract_lessons_from_events(events: list[Any]) -> list[dict[str, str]]:
    """Extract lessons from a list of AgentEvent objects after a session."""
    lessons: list[dict[str, str]] = []
    seen_failures: set[str] = set()

    for ev in events:
        meta = getattr(ev, "metadata", None) or {}
        ev_type = getattr(ev, "type", "")

        # Failed tool call → error lesson
        if ev_type == "tool_result" and meta.get("error"):
            tool = meta.get("tool_name", "unknown")
            content = getattr(ev, "content", "") or ""
            key = f"{tool}:{content[:50]}"
            if key not in seen_failures:
                seen_failures.add(key)
                lessons.append({
                    "tool": tool,
                    "category": "writing",
                    "severity": "error",
                    "description": f"工具 {tool} 执行失败: {content[:200]}",
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })

        # Loop force stop → warning lesson
        if ev_type == "warning" and meta.get("code") == "LOOP_FORCE_STOP":
            lessons.append({
                "tool": "agent_loop",
                "category": "pipeline",
                "severity": "warning",
                "description": "Agent 进入死循环被强制停止 — 任务可能需要更明确的指令",
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

    return lessons
