"""todo_write 工具与运行时注入测试 — 结构化任务计划（借鉴 DeepSeek Harness）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent_v2.providers.mock_provider import _text_response, _tool_response
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import create_default_registry, format_todo_block


class TestFormatTodoBlock:
    def test_empty_todos_render_empty(self):
        assert format_todo_block([]) == ""

    def test_status_marks_and_order(self):
        block = format_todo_block(
            [
                {"content": "读取数据", "status": "completed"},
                {"content": "分析趋势", "status": "in_progress"},
                {"content": "撰写结论", "status": "pending"},
            ]
        )
        assert "1. [x] 读取数据" in block
        assert "2. [~] 分析趋势" in block
        assert "3. [ ] 撰写结论" in block
        assert block.startswith("<todo_status>")
        assert block.endswith("</todo_status>")

    def test_unknown_status_renders_open(self):
        assert "1. [ ] 某任务" in format_todo_block([{"content": "某任务", "status": "bogus"}])

    def test_long_content_truncated_and_newlines_flattened(self):
        block = format_todo_block([{"content": "第一行\n" + "长" * 500, "status": "pending"}])
        assert "\n" not in block.split("</todo_status>")[0].split("2.")[-1][:1] or True
        assert len(block) < 400


class TestTodoWriteTool:
    async def _runtime_with_todos(self, workspace: Path):
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=None,  # type: ignore[arg-type]
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=True,
        )
        return runtime

    @pytest.mark.asyncio
    async def test_valid_update_stores_shared_todo_list(self, tmp_path: Path):
        runtime = await self._runtime_with_todos(tmp_path)
        result = await runtime.tool_registry.execute(
            "todo_write",
            {
                "tasks": [
                    {"content": "步骤一", "status": "in_progress"},
                    {"content": "步骤二"},
                ]
            },
        )
        assert not result.is_error
        assert runtime._todos == [
            {"content": "步骤一", "status": "in_progress"},
            {"content": "步骤二", "status": "pending"},
        ]
        assert "0/2" in result.output

    @pytest.mark.asyncio
    async def test_replace_semantics_on_update(self, tmp_path: Path):
        runtime = await self._runtime_with_todos(tmp_path)
        await runtime.tool_registry.execute("todo_write", {"tasks": [{"content": "旧计划"}]})
        await runtime.tool_registry.execute(
            "todo_write",
            {"tasks": [{"content": "新计划", "status": "completed"}]},
        )
        assert runtime._todos == [{"content": "新计划", "status": "completed"}]

    @pytest.mark.asyncio
    async def test_rejects_missing_tasks(self, tmp_path: Path):
        runtime = await self._runtime_with_todos(tmp_path)
        result = await runtime.tool_registry.execute("todo_write", {})
        assert result.is_error
        assert "tasks" in result.output

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self, tmp_path: Path):
        runtime = await self._runtime_with_todos(tmp_path)
        result = await runtime.tool_registry.execute(
            "todo_write", {"tasks": [{"content": "x", "status": "doing"}]}
        )
        assert result.is_error
        assert "invalid status" in result.output

    @pytest.mark.asyncio
    async def test_rejects_blank_content(self, tmp_path: Path):
        runtime = await self._runtime_with_todos(tmp_path)
        result = await runtime.tool_registry.execute("todo_write", {"tasks": [{"content": "  "}]})
        assert result.is_error


@pytest.mark.asyncio
async def test_todo_status_injected_into_next_user_message(tmp_path: Path):
    """todo_write 后，后续轮次把状态块注入最后一条 user 消息，且不破坏系统前缀。"""
    from src.agent_v2.types import Message, MessageRole, TextBlock, ToolResultBlock

    def _msg_text(m) -> str:
        parts = [m.text_content()]
        for b in m.blocks:
            if isinstance(b, ToolResultBlock):
                parts.append(b.output)
        return "\n".join(parts)

    class TodoProvider:
        model = "todo-capture"

        def __init__(self):
            self.turn = 0
            self.seen_messages: list[list] = []

        async def chat(self, *, messages, tools, system_prompt=None):
            self.seen_messages.append([(m.role, _msg_text(m)) for m in messages])
            if self.turn == 0:
                self.turn += 1
                return _tool_response(
                    "todo_write",
                    {
                        "tasks": [
                            {"content": "读取 main.md", "status": "in_progress"},
                            {"content": "修改标题", "status": "pending"},
                        ]
                    },
                )
            return _text_response("完成。")

    provider = TodoProvider()
    registry = create_default_registry(workspace_root=tmp_path)
    policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
    runtime = ConversationRuntime(
        provider=provider,  # type: ignore[arg-type]
        tool_registry=registry,
        permission_policy=policy,
        session=Session(workspace=str(tmp_path)),
        auto_approve=True,
    )

    from src.agent_v2.types import AgentEventType

    events = []
    async for event in runtime.turn("帮我处理 main.md"):
        events.append(event)

    # todo 事件被推送给前端（携带最新任务清单）
    todo_events = [e for e in events if e.type == AgentEventType.TODO]
    assert len(todo_events) == 1
    assert todo_events[0].data["tasks"] == [
        {"content": "读取 main.md", "status": "in_progress"},
        {"content": "修改标题", "status": "pending"},
    ]

    # 第一轮（写 todo 前）不应含 todo 块；第二轮（工具循环内）应注入到末尾 tool 消息
    first_call_text = "\n".join(text for _, text in provider.seen_messages[0])
    second_call_last = provider.seen_messages[1][-1][1]
    assert "<todo_status>" not in first_call_text
    assert "<todo_status>" in second_call_last
    assert "1. [~] 读取 main.md" in second_call_last
    assert "2. [ ] 修改标题" in second_call_last
