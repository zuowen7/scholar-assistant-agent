"""messages_to_anthropic 连续 user 消息合并测试。

验证 Anthropic 格式下连续 tool_result 和普通 user 消息被正确合并：
- 单 tool_result 行为不变
- 连续多个 tool_result 合并为单个 user 消息
- tool_result 后跟普通 user 消息合并
- 普通消息序列不受影响
"""
import pytest

from src.agent._llm_helpers import messages_to_anthropic
from src.agent.models import Message, ToolCall


class TestAnthropicMsgMerge:
    """H2: messages_to_anthropic 连续 user 合并"""

    def test_t1_single_tool_result_unchanged(self):
        """单 tool_result 仍为单 user 消息。"""
        msgs = [
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc1", name="read_file", arguments={"path": "a.txt"}),
            ]),
            Message(role="tool", content="file content", tool_call_id="tc1"),
        ]
        _, anthropic_msgs = messages_to_anthropic(msgs)
        user_msgs = [m for m in anthropic_msgs if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"][0]["type"] == "tool_result"

    def test_t2_two_consecutive_tool_results_merged(self):
        """连续两个 tool_result 合并为一个 user。"""
        msgs = [
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc1", name="read_file", arguments={"path": "a.txt"}),
                ToolCall(id="tc2", name="read_file", arguments={"path": "b.txt"}),
            ]),
            Message(role="tool", content="content A", tool_call_id="tc1"),
            Message(role="tool", content="content B", tool_call_id="tc2"),
        ]
        _, anthropic_msgs = messages_to_anthropic(msgs)
        user_msgs = [m for m in anthropic_msgs if m["role"] == "user"]
        assert len(user_msgs) == 1
        blocks = user_msgs[0]["content"]
        assert len(blocks) == 2
        assert blocks[0]["tool_use_id"] == "tc1"
        assert blocks[1]["tool_use_id"] == "tc2"

    def test_t3_three_consecutive_tool_results(self):
        """连续三个 tool_result 合并。"""
        msgs = [
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc1", name="x", arguments={}),
                ToolCall(id="tc2", name="y", arguments={}),
                ToolCall(id="tc3", name="z", arguments={}),
            ]),
            Message(role="tool", content="A", tool_call_id="tc1"),
            Message(role="tool", content="B", tool_call_id="tc2"),
            Message(role="tool", content="C", tool_call_id="tc3"),
        ]
        _, anthropic_msgs = messages_to_anthropic(msgs)
        user_msgs = [m for m in anthropic_msgs if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert len(user_msgs[0]["content"]) == 3

    def test_t4_tool_result_then_user_merged(self):
        """tool_result 后跟普通 user 消息合并为一个 user。"""
        msgs = [
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc1", name="read_file", arguments={}),
            ]),
            Message(role="tool", content="file content", tool_call_id="tc1"),
            Message(role="user", content="Thanks, now summarize."),
        ]
        _, anthropic_msgs = messages_to_anthropic(msgs)
        user_msgs = [m for m in anthropic_msgs if m["role"] == "user"]
        assert len(user_msgs) == 1
        blocks = user_msgs[0]["content"]
        assert any(b.get("type") == "tool_result" for b in blocks)
        assert any(b.get("type") == "text" or (isinstance(b.get("text"), str) and "summarize" in b.get("text", "")) for b in blocks)

    def test_t5_normal_sequence_unchanged(self):
        """普通消息序列不受影响。"""
        msgs = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi!"),
            Message(role="user", content="How are you?"),
        ]
        system, anthropic_msgs = messages_to_anthropic(msgs)
        assert "helpful" in system
        roles = [m["role"] for m in anthropic_msgs]
        assert roles == ["user", "assistant", "user"]

    def test_t6_empty_messages(self):
        """空消息列表不崩溃。"""
        system, anthropic_msgs = messages_to_anthropic([])
        assert anthropic_msgs == []

    def test_t7_tool_result_then_assistant_not_merged(self):
        """tool_result 后跟 assistant 不合并（中间有间隔）。"""
        msgs = [
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc1", name="x", arguments={}),
            ]),
            Message(role="tool", content="result", tool_call_id="tc1"),
            Message(role="assistant", content="Done!"),
            Message(role="user", content="Next question"),
        ]
        _, anthropic_msgs = messages_to_anthropic(msgs)
        roles = [m["role"] for m in anthropic_msgs]
        # assistant(tool_calls) -> user(tool_result) -> assistant -> user — no consecutive users
        assert roles == ["assistant", "user", "assistant", "user"]

    def test_t8_two_separate_tool_rounds(self):
        """两轮独立的 tool call 各自合并，不跨轮合并。"""
        msgs = [
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc1", name="x", arguments={}),
            ]),
            Message(role="tool", content="A", tool_call_id="tc1"),
            Message(role="assistant", content="", tool_calls=[
                ToolCall(id="tc2", name="y", arguments={}),
            ]),
            Message(role="tool", content="B", tool_call_id="tc2"),
        ]
        _, anthropic_msgs = messages_to_anthropic(msgs)
        user_msgs = [m for m in anthropic_msgs if m["role"] == "user"]
        assert len(user_msgs) == 2
        # Each has 1 tool_result block
        assert len(user_msgs[0]["content"]) == 1
        assert len(user_msgs[1]["content"]) == 1
