"""ReAct 轨迹记录器 — 记录 Agent 执行过程的完整轨迹。

每次任务完成后，将完整的 ReAct 轨迹保存为 JSONL 格式（兼容 ShareGPT），
供 Skill 生成和后台审查使用。

轨迹结构：
- conversations: 对话轮次列表（system/user/assistant/tool）
- metadata: 模型、耗时、成功/失败等元信息
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrajectoryTurn:
    """轨迹中的单轮对话。

    Attributes:
        role: 角色（system/user/assistant/tool）。
        content: 消息内容。
        tool_name: 工具名称（仅 tool 角色时有值）。
        tool_args: 工具参数（仅 tool 角色时有值）。
        duration_ms: 耗时毫秒（仅 tool 角色时有值）。
    """

    role: str
    content: str = ""
    tool_name: str = ""
    tool_args: dict | None = None
    duration_ms: int = 0


@dataclass
class Trajectory:
    """一次完整的 Agent 任务轨迹。

    Attributes:
        query: 原始用户查询。
        turns: 对话轮次列表。
        final_answer: 最终回答。
        success: 是否成功完成。
        model: 使用的模型名称。
        total_duration_ms: 总耗时毫秒。
        created_at: 创建时间。
    """

    query: str = ""
    turns: list[TrajectoryTurn] = field(default_factory=list)
    final_answer: str = ""
    success: bool = False
    model: str = ""
    total_duration_ms: int = 0
    created_at: str = ""

    def to_sharegpt(self) -> list[dict[str, str]]:
        """转换为 ShareGPT 格式。

        Returns:
            ShareGPT 格式的对话列表。
        """
        role_map = {
            "system": "system",
            "user": "human",
            "assistant": "gpt",
            "tool": "tool",
        }
        result: list[dict[str, str]] = []
        for turn in self.turns:
            from_role = role_map.get(turn.role, turn.role)
            result.append({"from": from_role, "value": turn.content})
        if self.final_answer:
            result.append({"from": "gpt", "value": self.final_answer})
        return result


class TrajectoryRecorder:
    """ReAct 轨迹记录器。

    记录每次 Agent 任务的完整执行过程，保存为 JSONL 文件。
    成功和失败的轨迹分别存储，便于后续分析和 Skill 生成。

    Attributes:
        data_dir: 轨迹文件存储目录。
    """

    def __init__(self, data_dir: str | Path = "data/agent/trajectories") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._current: Trajectory | None = None
        self._start_time: float = 0.0

    def start(self, query: str, model: str = "") -> Trajectory:
        """开始记录一次新轨迹。

        Args:
            query: 用户查询。
            model: 模型名称。

        Returns:
            新的 Trajectory 实例。
        """
        self._current = Trajectory(
            query=query,
            model=model,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        self._start_time = time.monotonic()
        return self._current

    def add_turn(
        self,
        role: str,
        content: str,
        tool_name: str = "",
        tool_args: dict | None = None,
        duration_ms: int = 0,
    ) -> None:
        """添加一轮对话到当前轨迹。

        Args:
            role: 角色。
            content: 内容。
            tool_name: 工具名称。
            tool_args: 工具参数。
            duration_ms: 耗时。
        """
        if self._current is None:
            return
        self._current.turns.append(TrajectoryTurn(
            role=role,
            content=content,
            tool_name=tool_name,
            tool_args=tool_args,
            duration_ms=duration_ms,
        ))

    def finish(self, final_answer: str, success: bool = True) -> Trajectory | None:
        """结束当前轨迹并保存。

        Args:
            final_answer: 最终回答。
            success: 是否成功。

        Returns:
            完成的 Trajectory 实例，无活跃轨迹时返回 None。
        """
        if self._current is None:
            return None

        self._current.final_answer = final_answer
        self._current.success = success
        self._current.total_duration_ms = int((time.monotonic() - self._start_time) * 1000)

        self._save(self._current)
        trajectory = self._current
        self._current = None
        return trajectory

    def _save(self, trajectory: Trajectory) -> None:
        """将轨迹保存为 JSONL 文件。

        Args:
            trajectory: 要保存的轨迹。
        """
        filename = "success.jsonl" if trajectory.success else "failed.jsonl"
        filepath = self.data_dir / filename

        record = {
            "conversations": trajectory.to_sharegpt(),
            "metadata": {
                "query": trajectory.query,
                "model": trajectory.model,
                "success": trajectory.success,
                "total_duration_ms": trajectory.total_duration_ms,
                "turn_count": len(trajectory.turns),
                "created_at": trajectory.created_at,
            },
        }

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(
                "轨迹已保存: %s (%d 轮, %dms)",
                filename, len(trajectory.turns), trajectory.total_duration_ms,
            )
        except Exception as e:
            logger.error("保存轨迹失败: %s", e)

    def get_recent(self, limit: int = 10, success_only: bool = False) -> list[dict]:
        """获取最近的轨迹记录。

        Args:
            limit: 返回上限。
            success_only: 是否只返回成功的轨迹。

        Returns:
            轨迹记录列表。
        """
        records: list[dict] = []
        files = ["success.jsonl"]
        if not success_only:
            files.append("failed.jsonl")

        for filename in files:
            filepath = self.data_dir / filename
            if not filepath.exists():
                continue
            try:
                with open(filepath, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except Exception:
                continue

        # 按 created_at 降序
        records.sort(key=lambda r: r.get("metadata", {}).get("created_at", ""), reverse=True)
        return records[:limit]
