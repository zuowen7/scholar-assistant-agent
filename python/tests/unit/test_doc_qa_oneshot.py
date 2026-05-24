"""文档问答一次性短路（Path A）单元测试。

验证：有文档内容、非文件改动意图的问题，走单次 LLM 流式回答，
不进 ReAct、不产生任何 tool_call 事件。
"""

from __future__ import annotations

import json

import pytest

from routers.agent import _has_mutation_intent, _oneshot_doc_qa_stream


class _FakeLLM:
    """假 LLM：把回答按 token 流式吐出，记录是否被传入了 tools。"""

    def __init__(self, answer: str):
        self.answer = answer
        self.tools_seen = "unset"

    async def stream(self, msgs, tools=None):
        self.tools_seen = tools
        # 把系统/用户消息暴露给断言
        self.last_msgs = msgs
        for ch in self.answer:
            yield {"content": ch}, None
        yield None, {"message": {"content": self.answer}}


class _FakeAgent:
    def __init__(self, answer: str):
        self.llm = _FakeLLM(answer)
        self.closed = False

    async def close(self):
        self.closed = True


class TestMutationIntent:
    def test_question_is_not_mutation(self):
        assert _has_mutation_intent("这篇文章写得怎么样") is False
        assert _has_mutation_intent("帮我总结一下这篇论文") is False
        assert _has_mutation_intent("这段论证有什么漏洞") is False

    def test_file_ops_are_mutation(self):
        assert _has_mutation_intent("把结论写回文件") is True
        assert _has_mutation_intent("帮我创建文件 draft.md") is True
        assert _has_mutation_intent("run the build script") is True


class TestOneShotDocQA:
    @pytest.mark.asyncio
    async def test_streams_answer_without_tools(self):
        agent = _FakeAgent("这篇文章结构清晰。")
        events = [ev async for ev in _oneshot_doc_qa_stream(
            agent, "这篇文章写得怎么样", "# 标题\n正文内容……")]

        types = [json.loads(ev["data"])["type"] for ev in events]

        # 关键：没有任何 tool_call / ReAct 事件
        assert "tool_call" not in types
        assert "await_approval" not in types
        # 正确的事件序列
        assert types[0] == "session_started"
        assert "response" in types
        assert types[-1] == "done"
        # 最终答案正确
        response_ev = next(ev for ev in events if json.loads(ev["data"])["type"] == "response")
        assert json.loads(response_ev["data"])["content"] == "这篇文章结构清晰。"
        # 明确不带工具调用 LLM
        assert agent.llm.tools_seen is None
        # 文档内容确实被塞进了 prompt
        assert "正文内容" in agent.llm.last_msgs[1].content

    @pytest.mark.asyncio
    async def test_empty_model_output_has_fallback(self):
        agent = _FakeAgent("")
        events = [ev async for ev in _oneshot_doc_qa_stream(agent, "总结一下", "文档")]
        response_ev = next(ev for ev in events if json.loads(ev["data"])["type"] == "response")
        assert json.loads(response_ev["data"])["content"]  # 非空兜底
