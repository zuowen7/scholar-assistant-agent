"""DeepSeek 供应商适配回归测试 — reasoning_content 回传、缓存用量、思考模式参数。"""

from __future__ import annotations

import json

import httpx
import pytest

from src.agent_v2.providers.openai_compat import OpenAiCompatProvider
from src.agent_v2.types import (
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolResultBlock,
    ToolUseBlock,
)


def _assistant_with_tools(reasoning: str = "先想一下") -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        blocks=[
            ThinkingBlock(thinking=reasoning),
            ToolUseBlock(id="tc_1", name="read_file", input='{"path": "a.md"}'),
        ],
    )


def _assistant_text_only(reasoning: str = "先想一下") -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        blocks=[ThinkingBlock(thinking=reasoning), TextBlock(text="这是最终答案")],
    )


class TestReasoningEchoBack:
    def test_tool_call_turn_echoes_reasoning_content(self):
        provider = OpenAiCompatProvider(api_key="k", model="deepseek-v4-flash")
        messages = _build_messages_for_test(provider, [_assistant_with_tools("分析文件结构")])
        assistant = messages[0]
        assert assistant["reasoning_content"] == "分析文件结构"
        assert assistant["tool_calls"][0]["function"]["name"] == "read_file"

    def test_text_only_turn_omits_reasoning(self):
        provider = OpenAiCompatProvider(api_key="k", model="deepseek-v4-flash")
        messages = _build_messages_for_test(provider, [_assistant_text_only("想一下")])
        assert "reasoning_content" not in messages[0]
        assert messages[0]["content"] == "这是最终答案"

    def test_tool_result_and_reasoned_assistant_roundtrip(self):
        provider = OpenAiCompatProvider(api_key="k", model="deepseek-v4-flash")
        msgs = [
            Message(role=MessageRole.USER, blocks=[TextBlock(text="读一下 a.md")]),
            _assistant_with_tools("需要读取文件"),
            Message(
                role=MessageRole.TOOL,
                blocks=[
                    ToolResultBlock(tool_use_id="tc_1", tool_name="read_file", output="文件内容")
                ],
            ),
        ]
        built = _build_messages_for_test(provider, msgs)
        assert [m["role"] for m in built] == ["user", "assistant", "tool"]
        assert built[1]["reasoning_content"] == "需要读取文件"
        assert built[2]["tool_call_id"] == "tc_1"
        assert built[2]["content"] == "文件内容"


def _build_messages_for_test(provider: OpenAiCompatProvider, msgs: list[Message]) -> list[dict]:
    return provider._build_messages(msgs, system_prompt=None)


@pytest.mark.asyncio
async def test_non_stream_tool_call_only_turn_preserves_reasoning():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": None,
                                "reasoning_content": "用户要读文件",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path": "a.md"}',
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            ),
        )

    provider = OpenAiCompatProvider(api_key="k", model="deepseek-v4-flash")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = await provider.chat([Message(role=MessageRole.USER, blocks=[TextBlock(text="读 a.md")])])
    assert resp.stop_reason == "tool_use"
    thinkings = [b for b in resp.blocks if isinstance(b, ThinkingBlock)]
    assert len(thinkings) == 1
    assert thinkings[0].thinking == "用户要读文件"
    tools = [b for b in resp.blocks if isinstance(b, ToolUseBlock)]
    assert tools[0].name == "read_file"
    await provider.close()


@pytest.mark.asyncio
async def test_usage_cache_fields_mapped_from_deepseek():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {
                    "choices": [{"finish_reason": "stop", "message": {"content": "好"}}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "prompt_cache_hit_tokens": 80,
                        "prompt_cache_miss_tokens": 20,
                    },
                }
            ),
        )

    provider = OpenAiCompatProvider(api_key="k", model="deepseek-v4-flash")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = await provider.chat([Message(role=MessageRole.USER, blocks=[TextBlock(text="hi")])])
    assert resp.usage.cache_read_tokens == 80
    assert resp.usage.cache_creation_tokens == 20
    assert resp.usage.input_tokens == 100
    await provider.close()


@pytest.mark.asyncio
async def test_stream_final_response_includes_merged_reasoning():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=(
                'data: {"choices":[{"delta":{"reasoning_content":"先分"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{"reasoning_content":"析一下"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{"content":"结论"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n"
            ),
        )

    provider = OpenAiCompatProvider(
        base_url="https://api.deepseek.com/v1",
        api_key="k",
        model="deepseek-v4-flash",
        thinking_mode="enabled",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    final: ProviderResponse | None = None
    async for chunk in provider.chat_stream(
        [Message(role=MessageRole.USER, blocks=[TextBlock(text="hi")])]
    ):
        if isinstance(chunk, ProviderResponse):
            final = chunk

    assert final is not None
    thinkings = [b for b in final.blocks if isinstance(b, ThinkingBlock)]
    assert len(thinkings) == 1
    assert thinkings[0].thinking == "先分析一下"
    texts = [b for b in final.blocks if isinstance(b, TextBlock)]
    assert texts[0].text == "结论"
    await provider.close()


@pytest.mark.asyncio
async def test_thinking_enabled_omits_temperature():
    request_body: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = OpenAiCompatProvider(
        base_url="https://api.deepseek.com/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
        thinking_mode="enabled",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async for _ in provider.chat_stream(
        [Message(role=MessageRole.USER, blocks=[TextBlock(text="hi")])]
    ):
        pass

    assert request_body["thinking"] == {"type": "enabled"}
    assert "temperature" not in request_body
    await provider.close()
