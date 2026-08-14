"""openclaw 式消息去重测试 — 重复用户消息不污染上下文，重试用新回答替换旧回答。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent_v2.providers.mock_provider import _text_response
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import create_default_registry
from src.agent_v2.types import Message, MessageRole, TextBlock, ToolResultBlock


def _make_runtime(tmp_path: Path, provider) -> ConversationRuntime:
    registry = create_default_registry(workspace_root=tmp_path)
    policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
    return ConversationRuntime(
        provider=provider,
        tool_registry=registry,
        permission_policy=policy,
        session=Session(workspace=str(tmp_path)),
        auto_approve=True,
    )


class _TextProvider:
    model = "dedup-test"

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.calls = 0

    async def chat(self, *, messages, tools, system_prompt=None):
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return _text_response(answer)


@pytest.mark.asyncio
async def test_duplicate_user_message_is_deduped_and_answer_replaced(tmp_path: Path):
    provider = _TextProvider(["第一次回答", "第二次回答（重试）"])
    runtime = _make_runtime(tmp_path, provider)

    async for _ in runtime.turn("帮我整理文献"):
        pass
    async for _ in runtime.turn("帮我整理文献"):  # 完全相同的重复发送
        pass

    messages = runtime.session.messages
    roles = [m.role for m in messages]
    assert roles == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[0].text_content() == "帮我整理文献"
    assert messages[1].text_content() == "第二次回答（重试）"


@pytest.mark.asyncio
async def test_distinct_messages_append_normally(tmp_path: Path):
    provider = _TextProvider(["回答A", "回答B"])
    runtime = _make_runtime(tmp_path, provider)

    async for _ in runtime.turn("任务A"):
        pass
    async for _ in runtime.turn("任务B"):
        pass

    messages = runtime.session.messages
    assert [m.role for m in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert messages[0].text_content() == "任务A"
    assert messages[2].text_content() == "任务B"


@pytest.mark.asyncio
async def test_whitespace_only_difference_counts_as_duplicate(tmp_path: Path):
    provider = _TextProvider(["回答1", "回答2"])
    runtime = _make_runtime(tmp_path, provider)

    async for _ in runtime.turn("  写个摘要  "):
        pass
    async for _ in runtime.turn("写个摘要"):
        pass

    assert len(runtime.session.messages) == 2


def test_remove_trailing_messages_since_last_user():
    session = Session(workspace="C:/papers")
    session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="任务")]))
    session.append(Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="回答")]))
    session.append(
        Message(
            role=MessageRole.TOOL,
            blocks=[ToolResultBlock(tool_use_id="t1", tool_name="read_file", output="x")],
        )
    )

    removed = session.remove_trailing_messages_since_last_user()

    assert removed == 2
    assert [m.role for m in session.messages] == [MessageRole.USER]


def test_remove_trailing_messages_empty_and_user_only_sessions():
    empty = Session(workspace="C:/papers")
    assert empty.remove_trailing_messages_since_last_user() == 0

    user_only = Session(workspace="C:/papers")
    user_only.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="hi")]))
    assert user_only.remove_trailing_messages_since_last_user() == 0
