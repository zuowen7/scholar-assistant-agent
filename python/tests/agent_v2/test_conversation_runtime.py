"""ConversationRuntime 测试 — CR-001 ~ CR-054。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agent_v2.hooks import HookPoint, HookResult, HookRunner
from src.agent_v2.providers.mock_provider import (
    MockProvider,
    Scenario,
    _text_response,
    _tool_response,
)
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, PermissionPolicy, policy_from_registry
from src.agent_v2.runtime.session import _ROTATE_AFTER_BYTES, Session
from src.agent_v2.tools.registry import ToolRegistry, ToolResult, create_default_registry
from src.agent_v2.types import (
    AgentEvent,
    AgentEventType,
    ApiError,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolResultBlock,
    ToolUseBlock,
)


async def _collect_events(runtime: ConversationRuntime, msg: str) -> list[AgentEvent]:
    events = []
    async for event in runtime.turn(msg):
        events.append(event)
    return events


def _event_types(events: list[AgentEvent]) -> list[AgentEventType]:
    return [e.type for e in events]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "main.md").write_text("# Hello World", encoding="utf-8")
    return tmp_path


@pytest.fixture
def runtime(workspace: Path) -> ConversationRuntime:
    provider = MockProvider()
    registry = create_default_registry(workspace_root=workspace)
    policy = policy_from_registry(
        PermissionMode.WORKSPACE_WRITE,
        registry.permission_specs(),
    )
    session = Session(workspace=str(workspace), model="mock")
    return ConversationRuntime(
        provider=provider, tool_registry=registry, permission_policy=policy, session=session
    )


# ============================================================================
# 6.1 基础对话流
# ============================================================================


class TestBasicFlow:
    @pytest.mark.asyncio
    async def test_cr001_single_text_reply(self, runtime: ConversationRuntime):
        """CR-001: user → LLM(text) → response"""
        events = await _collect_events(runtime, "hello")
        types = _event_types(events)
        assert AgentEventType.SESSION_STARTED in types
        assert AgentEventType.TOKEN in types
        assert AgentEventType.RESPONSE in types
        assert AgentEventType.DONE in types

    @pytest.mark.asyncio
    async def test_non_streaming_fallback_records_provider_usage_once(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        class NonStreamingProvider:
            model = "test-model"

            async def chat(self, **kwargs):
                return ProviderResponse(
                    blocks=[TextBlock(text="done")],
                    usage=TokenUsage(input_tokens=11, output_tokens=7),
                )

        monkeypatch.setenv("SCHOLAR_AGENT_STREAM", "0")
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        rt = ConversationRuntime(
            provider=NonStreamingProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace), model="test-model"),
        )

        await _collect_events(rt, "hello")

        assert rt.usage.total_input == 11
        assert rt.usage.total_output == 7
        assert rt.usage.call_count == 1

    @pytest.mark.asyncio
    async def test_cr002_tool_call_then_reply(self, workspace: Path):
        """CR-002: user → tool_call → execute → tool_result → reply"""
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "r0",
                    trigger_patterns=["read it"],
                    turn_index=0,
                    response_factory=lambda m, t: _tool_response(
                        "read_file", {"file_path": "main.md"}
                    ),
                ),
                Scenario(
                    "r1",
                    trigger_patterns=["read it"],
                    turn_index=1,
                    response_factory=lambda m, t: _text_response(
                        "The file contains 'Hello World'."
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "read it")
        types = _event_types(events)
        assert AgentEventType.TOOL_CALL in types
        assert AgentEventType.TOOL_RESULT in types
        assert AgentEventType.RESPONSE in types
        # Verify tool result contains file content
        tool_results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        assert any("Hello" in e.data.get("output", "") for e in tool_results)

    @pytest.mark.asyncio
    async def test_invalid_truncated_tool_json_is_not_executed_or_sent_for_approval(
        self, workspace: Path
    ):
        class TruncatedProvider:
            model = "truncated"

            def __init__(self):
                self.calls = 0

            async def chat(self, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return ProviderResponse(
                        blocks=[
                            ToolUseBlock(
                                id="write-truncated",
                                name="write_file",
                                input='{"file_path":"figure.py","content":"unterminated',
                            )
                        ],
                        stop_reason="length",
                    )
                return _text_response("Recovered with a smaller payload.")

        provider = TruncatedProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=False,
        )

        events = await _collect_events(rt, "create a figure script")

        assert not (workspace / "figure.py").exists()
        assert AgentEventType.AWAIT_APPROVAL not in _event_types(events)
        failure = next(
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT
            and event.data.get("id") == "write-truncated"
        )
        assert failure.data["is_error"] is True
        assert failure.data["status"] == "error"
        assert "invalid or truncated JSON" in failure.data["output"]
        assert any(
            event.type == AgentEventType.RESPONSE
            and event.data.get("text") == "Recovered with a smaller payload."
            for event in events
        )

    @pytest.mark.asyncio
    async def test_tool_turn_resets_premature_completion_text(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "tool_with_text",
                    trigger_patterns=["inspect"],
                    turn_index=0,
                    response_factory=lambda m, t: ProviderResponse(
                        blocks=[
                            TextBlock(text="The task is complete."),
                            ToolUseBlock(
                                id="read_1",
                                name="read_file",
                                input=json.dumps({"file_path": "main.md"}),
                            ),
                        ],
                        stop_reason="tool_use",
                    ),
                ),
                Scenario(
                    "final",
                    trigger_patterns=["inspect"],
                    turn_index=1,
                    response_factory=lambda m, t: _text_response("Confirmed final response."),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
        )

        events = await _collect_events(rt, "inspect")
        resets = [
            event
            for event in events
            if event.type == AgentEventType.WARNING and event.data.get("reset_stream")
        ]

        assert len(resets) == 1
        assert any(
            event.type == AgentEventType.RESPONSE
            and event.data.get("text") == "Confirmed final response."
            for event in events
        )

    @pytest.mark.asyncio
    async def test_cr004_event_sequence(self, runtime: ConversationRuntime):
        """CR-004: 事件序列正确"""
        events = await _collect_events(runtime, "hello")
        types = _event_types(events)
        # SESSION_STARTED first, DONE last
        assert types[0] == AgentEventType.SESSION_STARTED
        assert types[-1] == AgentEventType.DONE
        # RESPONSE before DONE
        if AgentEventType.RESPONSE in types:
            assert types.index(AgentEventType.RESPONSE) < types.index(AgentEventType.DONE)

    @pytest.mark.asyncio
    async def test_selection_turn_exposes_only_selection_safe_tools(self, workspace: Path):
        class CapturingProvider:
            model = "capture"

            def __init__(self):
                self.tool_names: list[str] = []

            async def chat(self, *, messages, tools, system_prompt=None):
                self.tool_names = [tool.name for tool in tools]
                return _text_response("Reviewed the active selection.")

        provider = CapturingProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            edit_scope={
                "file_path": "main.md",
                "start_line": 1,
                "start_column": 1,
                "end_line": 1,
                "end_column": 14,
                "text": "# Hello World",
            },
        )

        events = await _collect_events(runtime, "polish the active selection")

        assert AgentEventType.RESPONSE in _event_types(events)
        assert "str_replace" in provider.tool_names
        assert "read_file" not in provider.tool_names
        assert "grep_files" not in provider.tool_names
        assert "run_command" not in provider.tool_names
        assert "write_file" not in provider.tool_names

    @pytest.mark.asyncio
    async def test_selection_edit_finalizes_without_exposing_more_tools(self, workspace: Path):
        class SelectionEditProvider:
            model = "selection-edit"

            def __init__(self):
                self.turn_index = 0
                self.tool_names_by_turn: list[list[str]] = []
                self.system_prompts: list[str] = []

            async def chat(self, *, messages, tools, system_prompt=None):
                self.tool_names_by_turn.append([tool.name for tool in tools])
                self.system_prompts.append(system_prompt or "")
                if self.turn_index == 0:
                    self.turn_index += 1
                    return _tool_response(
                        "str_replace",
                        {
                            "file_path": "main.md",
                            "old_string": "# Hello World",
                            "new_string": "# Polished World",
                        },
                    )
                return _text_response("已生成并应用选区修改。")

        provider = SelectionEditProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=True,
            edit_scope={
                "file_path": "main.md",
                "start_line": 1,
                "start_column": 1,
                "end_line": 1,
                "end_column": 14,
                "text": "# Hello World",
            },
        )

        events = await _collect_events(runtime, "polish the active selection")

        assert workspace.joinpath("main.md").read_text(encoding="utf-8") == "# Polished World"
        assert provider.tool_names_by_turn[0] == ["str_replace"]
        assert provider.tool_names_by_turn[1] == []
        assert "Do not call any more tools" in provider.system_prompts[1]
        assert AgentEventType.RESPONSE in _event_types(events)

    @pytest.mark.asyncio
    async def test_repeated_identical_tool_loop_uses_total_budget(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "loop",
                    trigger_patterns=[],
                    response_factory=lambda m, t: _tool_response(
                        "read_file", {"file_path": "main.md"}
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            max_steps=20,
            max_tool_calls=4,
        )

        events = await _collect_events(runtime, "keep reading")
        tool_calls = [event for event in events if event.type == AgentEventType.TOOL_CALL]

        assert len(tool_calls) == 5
        assert not any(event.type == AgentEventType.ERROR for event in events)
        assert runtime.session.meta.state == "PARTIAL"
        assert runtime.session.meta.outcome["stop_code"] == "tool_budget_exhausted"

    @pytest.mark.asyncio
    async def test_stopped_turn_never_exposes_dsml_tool_protocol(self, workspace: Path):
        protocol = (
            "<｜｜DSML｜｜tool_calls>"
            '<｜｜DSML｜｜invoke name="run_command">{"command":"python make.py"}'
            "</｜｜DSML｜｜tool_calls>"
        )
        provider = _ScriptedProvider(
            [
                _tool_response("read_file", {"file_path": "main.md"}),
                _tool_response("read_file", {"file_path": "main.md"}),
                _tool_response("read_file", {"file_path": "main.md"}),
                _text_response(protocol),
                _text_response(protocol),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=Session(workspace=str(workspace)),
            max_tool_calls=2,
        )

        events = await _collect_events(runtime, "repeat until stopped")
        visible = "\n".join(
            str(event.data.get("text", "")) + str(event.data.get("token", "")) for event in events
        )

        assert "DSML" not in visible
        partial = next(event for event in events if event.type == AgentEventType.RESPONSE)
        assert partial.data["partial"] is True
        assert partial.data["stop_code"] == "tool_budget_exhausted"
        assert "tool_budget_exhausted" in partial.data["text"]

    @pytest.mark.asyncio
    async def test_academic_content_is_not_blocked_by_runtime_fact_validation(
        self, workspace: Path
    ):
        (workspace / "draft").mkdir()
        manuscript = workspace / "draft" / "main.md"
        manuscript.write_text("PCA结果待计算。\n", encoding="utf-8")
        registry = create_default_registry(workspace_root=workspace)
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=Session(workspace=str(workspace)),
            auto_approve=True,
        )
        call = ToolUseBlock(
            id="prompt-governed-content",
            name="str_replace",
            input=json.dumps(
                {
                    "file_path": "draft/main.md",
                    "old_string": "PCA结果待计算。",
                    "new_string": "PCA累计方差解释率为78.3%。",
                },
                ensure_ascii=False,
            ),
        )

        events = [event async for event in runtime._execute_tool(call)]

        assert not any(
            event.type == AgentEventType.TOOL_RESULT and event.data.get("is_error")
            for event in events
        )
        assert manuscript.read_text(encoding="utf-8") == "PCA累计方差解释率为78.3%。\n"
        assert any(event.type == AgentEventType.CHECKPOINT for event in events)

    @pytest.mark.asyncio
    async def test_skill_response_is_delivered_without_runtime_rewrite(self, workspace: Path):
        draft = "The reported interval is 95%."
        provider = _ScriptedProvider([_text_response(draft)])
        registry = create_default_registry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        session.meta.active_skills = ["nature_reviewer"]
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
        )

        events = await _collect_events(runtime, "Review the supplied manuscript.")

        responses = [
            event.data["text"] for event in events if event.type == AgentEventType.RESPONSE
        ]
        assert responses == [draft]
        assert provider._index == 1
        assert not any(
            event.type == AgentEventType.WARNING
            and event.data.get("code") == "response_grounding_retry"
            for event in events
        )
        assert session.meta.state == "COMPLETE"

    @pytest.mark.asyncio
    async def test_pending_write_is_recovered_instead_of_downgraded_to_chat(self, workspace: Path):
        (workspace / "draft").mkdir()
        manuscript = workspace / "draft" / "main.md"
        manuscript.write_text("Result pending.\n", encoding="utf-8")
        failed_write = ToolUseBlock(
            id="write-1",
            name="str_replace",
            input=json.dumps(
                {
                    "file_path": "draft/main.md",
                    "old_string": "Missing marker.",
                    "new_string": "ExplainedVariance PCA result is 78.3%.",
                }
            ),
        )
        recovered_write = ToolUseBlock(
            id="write-2",
            name="str_replace",
            input=json.dumps(
                {
                    "file_path": "draft/main.md",
                    "old_string": "Result pending.",
                    "new_string": "ExplainedVariance PCA result is 78.3%.",
                }
            ),
        )
        provider = _ScriptedProvider(
            [
                ProviderResponse(blocks=[failed_write], stop_reason="tool_use"),
                _tool_response("read_file", {"file_path": "draft/main.md"}),
                ProviderResponse(blocks=[recovered_write], stop_reason="tool_use"),
                _text_response("文件已写入并核验。"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            auto_approve=True,
        )

        events = await _collect_events(runtime, "write the verified result")

        assert session.meta.state == "COMPLETE"
        assert session.meta.pending_actions == []
        assert "78.3%" in manuscript.read_text(encoding="utf-8")
        assert any(event.type == AgentEventType.CHECKPOINT for event in events)

    @pytest.mark.asyncio
    async def test_pending_write_returns_one_honest_partial_without_forced_response_retry(
        self, workspace: Path
    ):
        (workspace / "draft").mkdir()
        manuscript = workspace / "draft" / "main.md"
        manuscript.write_text("Result pending.\n", encoding="utf-8")
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(
                            id="write-blocked",
                            name="str_replace",
                            input=json.dumps(
                                {
                                    "file_path": "draft/main.md",
                                    "old_string": "Missing marker.",
                                    "new_string": "Unsupported result is 78.3%.",
                                }
                            ),
                        )
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("先口头汇报。"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            auto_approve=True,
        )

        events = await _collect_events(runtime, "write the result")

        response = next(event for event in events if event.type == AgentEventType.RESPONSE)
        assert not any(
            event.type == AgentEventType.WARNING
            and event.data.get("code") == "pending_actions_retry"
            for event in events
        )
        assert response.data["partial"] is True
        assert response.data["stop_code"] == "pending_actions_remaining"
        assert provider._index == 2
        assert session.meta.state == "PARTIAL"
        assert session.meta.pending_actions
        assert manuscript.read_text(encoding="utf-8") == "Result pending.\n"

    @pytest.mark.asyncio
    async def test_continue_turn_recovers_pending_action_from_prior_turn(self, workspace: Path):
        target = str((workspace / "main.md").resolve())
        session = Session(workspace=str(workspace))
        session.record_pending_action(
            tool_name="write_file",
            target_path=target,
            error_code="invalid_tool_json",
            turn_id="prior-turn",
        )
        provider = _ScriptedProvider(
            [
                _tool_response(
                    "write_file",
                    {
                        "file_path": "main.md",
                        "content": "# Recovered deliverable\n",
                    },
                ),
                _text_response("已继续完成并核验。"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            auto_approve=True,
        )

        events = await _collect_events(runtime, "继续完成刚才未完成的任务")

        assert session.meta.state == "COMPLETE"
        assert session.meta.pending_actions == []
        assert (workspace / "main.md").read_text(encoding="utf-8") == "# Recovered deliverable\n"
        assert any(event.type == AgentEventType.CHECKPOINT for event in events)

    @pytest.mark.asyncio
    async def test_chunked_write_remains_pending_until_final_chunk(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                _tool_response(
                    "write_file",
                    {
                        "file_path": "deliverable.txt",
                        "content": "first\n",
                        "mode": "overwrite",
                        "final_chunk": False,
                    },
                ),
                _tool_response(
                    "write_file",
                    {
                        "file_path": "deliverable.txt",
                        "content": "second\n",
                        "mode": "append",
                        "final_chunk": True,
                    },
                ),
                _text_response("分块文件已完整写入。"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            auto_approve=True,
        )

        events = await _collect_events(runtime, "write the large deliverable in chunks")

        assert session.meta.state == "COMPLETE"
        assert session.meta.pending_actions == []
        assert (workspace / "deliverable.txt").read_text() == "first\nsecond\n"
        assert len(session.mutation_journal) == 2
        assert sum(event.type == AgentEventType.CHECKPOINT for event in events) == 2

    @pytest.mark.asyncio
    async def test_dirty_editor_file_blocks_disk_mutation_before_approval(self, workspace: Path):
        registry = create_default_registry(workspace_root=workspace)
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=Session(workspace=str(workspace)),
            auto_approve=False,
            editor_files=[
                {
                    "file_path": str(workspace / "main.md"),
                    "is_dirty": True,
                    "content_hash": "a" * 64,
                    "editor_version": 7,
                }
            ],
        )
        call = ToolUseBlock(
            id="dirty-edit",
            name="str_replace",
            input=json.dumps(
                {
                    "file_path": "main.md",
                    "old_string": "# Hello World",
                    "new_string": "# Changed",
                }
            ),
        )

        events = [event async for event in runtime._execute_tool(call)]

        assert AgentEventType.AWAIT_APPROVAL not in _event_types(events)
        result = next(event for event in events if event.type == AgentEventType.TOOL_RESULT)
        assert result.data["metadata"]["code"] == "dirty_editor_conflict"
        assert workspace.joinpath("main.md").read_text(encoding="utf-8") == "# Hello World"

    @pytest.mark.asyncio
    async def test_dirty_editor_conflict_stops_turn_without_model_retry_loop(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                _tool_response(
                    "write_file",
                    {"file_path": "main.md", "content": "# Changed"},
                ),
                _text_response("The editor has unsaved changes; save or resolve them first."),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            auto_approve=True,
            editor_files=[
                {
                    "file_path": str(workspace / "main.md"),
                    "is_dirty": True,
                    "content_hash": "a" * 64,
                    "editor_version": 7,
                }
            ],
        )

        events = await _collect_events(runtime, "replace main.md")

        results = [
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT
            and event.data.get("tool_name") == "write_file"
        ]
        assert len(results) == 1
        assert results[0].data["metadata"]["code"] == "dirty_editor_conflict"
        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "dirty_editor_conflict"
        assert len(session.meta.pending_actions) == 1
        assert workspace.joinpath("main.md").read_text(encoding="utf-8") == "# Hello World"

    @pytest.mark.asyncio
    async def test_cr005_empty_tool_calls(self, workspace: Path):
        """CR-005: LLM 返回无 tool_call（纯文本），直接结束"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "explain this concept")
        types = _event_types(events)
        assert AgentEventType.RESPONSE in types

    @pytest.mark.asyncio
    async def test_file_checkpoints_cover_every_file_with_resolved_paths(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "multi-write",
                    trigger_patterns=["update both"],
                    turn_index=0,
                    response_factory=lambda m, t: ProviderResponse(
                        blocks=[
                            ToolUseBlock(
                                id="write_a",
                                name="write_file",
                                input=json.dumps({"file_path": "a.md", "content": "A"}),
                            ),
                            ToolUseBlock(
                                id="write_b",
                                name="write_file",
                                input=json.dumps({"file_path": "b.md", "content": "B"}),
                            ),
                        ],
                        stop_reason="tool_use",
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=True,
        )

        events = await _collect_events(rt, "update both")
        checkpoints = [event for event in events if event.type == AgentEventType.CHECKPOINT]

        assert [Path(event.data["file"]) for event in checkpoints] == [
            (workspace / "a.md").resolve(),
            (workspace / "b.md").resolve(),
        ]
        assert [event.data["content"] for event in checkpoints] == ["A", "B"]
        assert all(event.data["content_truncated"] is False for event in checkpoints)
        assert [Path(record.path) for record in session.mutation_journal] == [
            (workspace / "a.md").resolve(),
            (workspace / "b.md").resolve(),
        ]
        assert all(record.before_exists is False for record in session.mutation_journal)


# ============================================================================
# 6.2 权限集成
# ============================================================================


class TestPermissionIntegration:
    @pytest.mark.asyncio
    async def test_missing_write_path_fails_before_requesting_approval(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "missing path",
                    trigger_patterns=["missing path"],
                    turn_index=0,
                    response_factory=lambda m, t: _tool_response(
                        "write_file",
                        {"content": "draft"},
                    ),
                ),
                Scenario(
                    "recover",
                    trigger_patterns=["missing path"],
                    turn_index=1,
                    response_factory=lambda m, t: _text_response(
                        "The invalid write was rejected before approval."
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=False,
        )

        events = await _collect_events(runtime, "missing path")

        assert AgentEventType.AWAIT_APPROVAL not in _event_types(events)
        failure = next(
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT and event.data.get("is_error")
        )
        assert failure.data["metadata"]["code"] == "invalid_tool_arguments"
        assert failure.data["metadata"]["fields"] == ["file_path"]

    @pytest.mark.asyncio
    async def test_run_command_preflight_fails_before_requesting_approval(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "run",
                    trigger_patterns=["run inline"],
                    turn_index=0,
                    response_factory=lambda m, t: _tool_response(
                        "run_command",
                        {"command": 'python -c "print(1)"'},
                    ),
                ),
                Scenario(
                    "recover",
                    trigger_patterns=["run inline"],
                    turn_index=1,
                    response_factory=lambda m, t: _text_response(
                        "The command was rejected before approval."
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=False,
        )

        events = await _collect_events(runtime, "run inline")

        assert AgentEventType.AWAIT_APPROVAL not in _event_types(events)
        failure = next(
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT and event.data.get("is_error")
        )
        assert failure.data["metadata"]["code"] == "command_policy_blocked"
        assert "inline code" in failure.data["output"].lower()

    @pytest.mark.asyncio
    async def test_cr010_tool_denied(self, workspace: Path):
        """CR-010: 工具被 Deny"""
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "write",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file", {"file_path": "out.txt", "content": "x"}
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.READ_ONLY, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "write something")
        types = _event_types(events)
        assert AgentEventType.TOOL_DENIED in types

    @pytest.mark.asyncio
    async def test_cr013_partial_deny(self, workspace: Path):
        """CR-013: 多工具部分拒绝"""
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "multi",
                    trigger_patterns=["multi"],
                    response_factory=lambda m, t: ProviderResponse(
                        blocks=[
                            ToolUseBlock(
                                id="tu_1",
                                name="read_file",
                                input=json.dumps({"file_path": "main.md"}),
                            ),
                            ToolUseBlock(
                                id="tu_2",
                                name="write_file",
                                input=json.dumps({"file_path": "out.txt", "content": "x"}),
                            ),
                        ],
                        stop_reason="tool_use",
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.READ_ONLY, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "multi operation")
        denied = [e for e in events if e.type == AgentEventType.TOOL_DENIED]
        results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        # read_file allowed, write_file denied
        assert len(results) >= 1  # read_file succeeded
        assert len(denied) >= 1  # write_file denied


# ============================================================================
# 6.3 会话管理
# ============================================================================


class TestSessionIntegration:
    @pytest.mark.asyncio
    async def test_cr020_session_auto_save(self, workspace: Path):
        """CR-020: 会话自动追加消息"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        await _collect_events(rt, "hello")
        # Session should have user + assistant messages
        assert session.message_count >= 2
        assert session.messages[0].role == MessageRole.USER
        assert session.messages[1].role == MessageRole.ASSISTANT

    @pytest.mark.asyncio
    async def test_auto_save_does_not_rotate_a_large_live_snapshot(self, workspace: Path):
        save_path = workspace / "large-session.jsonl"
        session = Session(workspace=str(workspace), model="mock")
        for index in range(24):
            session.append(
                Message(
                    role=MessageRole.USER,
                    blocks=[TextBlock(text=f"{index}:" + ("x" * 16_000))],
                )
            )
        session.save(save_path)
        assert save_path.stat().st_size >= _ROTATE_AFTER_BYTES
        session._save_path = str(save_path)
        registry = create_default_registry(workspace_root=workspace)
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE,
                registry.permission_specs(),
            ),
            session=session,
        )

        await _collect_events(runtime, "continue")

        assert save_path.is_file()
        assert not Path(str(save_path) + ".1").exists()
        loaded = Session.load(save_path)
        assert loaded.meta.state == "COMPLETE"
        assert loaded.messages[-1].text_content()


# ============================================================================
# 6.4 边缘测试
# ============================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_cr030_empty_user_message(self, runtime: ConversationRuntime):
        """CR-030: 空用户消息"""
        events = await _collect_events(runtime, "")
        types = _event_types(events)
        assert AgentEventType.ERROR in types

    @pytest.mark.asyncio
    async def test_cr031_whitespace_message(self, runtime: ConversationRuntime):
        """CR-031: 纯空白消息"""
        events = await _collect_events(runtime, "   \t\n  ")
        types = _event_types(events)
        assert AgentEventType.ERROR in types

    @pytest.mark.asyncio
    async def test_cr032_repeated_messages(self, workspace: Path):
        """CR-032: 重复消息独立处理"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events1 = await _collect_events(rt, "hello")
        events2 = await _collect_events(rt, "hello")
        # Both produce valid events
        assert any(e.type == AgentEventType.RESPONSE for e in events1)
        assert any(e.type == AgentEventType.RESPONSE for e in events2)


# ============================================================================
# 6.5 故障注入
# ============================================================================


class TestFaultInjection:
    @pytest.mark.asyncio
    async def test_reasoning_only_completion_is_recovered_once(self, workspace: Path):
        """A reasoning-only provider turn must continue instead of ending the task."""

        class ReasoningThenAnswerProvider:
            model = "mock"

            def __init__(self):
                self.calls = 0
                self.system_prompts: list[str] = []

            async def chat_stream(self, **kwargs):
                self.calls += 1
                self.system_prompts.append(kwargs["system_prompt"])
                if self.calls == 1:
                    yield ThinkingBlock(thinking="I should create the figure now.")
                    yield ProviderResponse(blocks=[], stop_reason="stop")
                    return
                yield TextBlock(text="Figure generation has started.")
                yield ProviderResponse(
                    blocks=[TextBlock(text="Figure generation has started.")],
                    stop_reason="stop",
                )

        provider = ReasoningThenAnswerProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(
            PermissionMode.WORKSPACE_WRITE,
            registry.permission_specs(),
        )
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace), model="mock"),
        )

        events = await _collect_events(runtime, "确认")

        assert provider.calls == 2
        assert provider.system_prompts[0] != provider.system_prompts[1]
        assert any(
            event.type == AgentEventType.WARNING
            and event.data.get("code") == "empty_model_response"
            and event.data.get("reset_stream") is True
            for event in events
        )
        assert any(
            event.type == AgentEventType.RESPONSE
            and event.data.get("text") == "Figure generation has started."
            for event in events
        )
        assert not [event for event in events if event.type == AgentEventType.ERROR]

    @pytest.mark.asyncio
    async def test_repeated_reasoning_only_completion_stops_after_three_attempts(
        self, workspace: Path
    ):
        """Semantic empty responses are retried finitely and end with actionable text."""

        class ReasoningOnlyProvider:
            model = "mock"

            def __init__(self):
                self.calls = 0

            async def chat_stream(self, **_kwargs):
                self.calls += 1
                yield ThinkingBlock(thinking="Still reasoning.")
                yield ProviderResponse(blocks=[], stop_reason="stop")

        provider = ReasoningOnlyProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(
            PermissionMode.WORKSPACE_WRITE,
            registry.permission_specs(),
        )
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace), model="mock"),
        )

        events = await _collect_events(runtime, "确认")
        errors = [event for event in events if event.type == AgentEventType.ERROR]

        assert provider.calls == 3
        assert len(errors) == 1
        assert "最终答复或工具调用" in errors[0].data["message"]
        assert "切换模型" in errors[0].data["message"]

    @pytest.mark.asyncio
    async def test_unexpected_stream_exception_is_not_blindly_retried(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Programming/schema errors must fail once instead of replaying the whole turn."""

        class BrokenStreamingProvider:
            model = "mock"

            def __init__(self):
                self.calls = 0

            async def chat_stream(self, **_kwargs):
                self.calls += 1
                if False:
                    yield None
                raise RuntimeError("stream parser bug")

        async def no_sleep(_delay: float):
            return None

        monkeypatch.setattr("src.agent_v2.runtime.conversation.asyncio.sleep", no_sleep)
        provider = BrokenStreamingProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(
            PermissionMode.WORKSPACE_WRITE,
            registry.permission_specs(),
        )
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace), model="mock"),
        )

        events = await _collect_events(runtime, "hello")

        assert provider.calls == 1
        assert not [event for event in events if event.type == AgentEventType.TOKEN]
        errors = [event for event in events if event.type == AgentEventType.ERROR]
        assert len(errors) == 1
        assert "stream parser bug" in errors[0].data["message"]

    @pytest.mark.asyncio
    async def test_cr040_llm_call_fails(self, workspace: Path):
        """CR-040: LLM 调用失败"""
        provider = MockProvider(error_on_turn={0: ApiError("LLM down", status_code=500)})
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "hello")
        types = _event_types(events)
        assert AgentEventType.ERROR in types
        assert any(
            "API error" in e.data.get("message", "")
            for e in events
            if e.type == AgentEventType.ERROR
        )

    @pytest.mark.asyncio
    async def test_cr041_tool_execution_exception(self, workspace: Path):
        """CR-041: 工具执行中途异常"""
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "boom",
                    trigger_patterns=["boom"],
                    response_factory=lambda m, t: _tool_response(
                        "read_file", {"file_path": "nonexistent.txt"}
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "boom boom")
        # Tool returns error result (is_error=True), runtime continues
        tool_results = [
            e
            for e in events
            if e.type == AgentEventType.TOOL_RESULT and e.data.get("is_error") is True
        ]
        assert len(tool_results) >= 1

    @pytest.mark.asyncio
    async def test_cr044_concurrent_requests(self, workspace: Path):
        """CR-044: 并发对话请求"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())

        async def single_turn(msg_id: int):
            session = Session(workspace=str(workspace))
            rt = ConversationRuntime(
                provider=MockProvider(),
                tool_registry=registry,
                permission_policy=policy,
                session=session,
            )
            events = await _collect_events(rt, "hello")
            return msg_id, events

        results = await asyncio.gather(*[single_turn(i) for i in range(5)])
        for _msg_id, events in results:
            assert any(e.type == AgentEventType.RESPONSE for e in events)


# ============================================================================
# 6.6 极限测试
# ============================================================================


class TestStress:
    @pytest.mark.asyncio
    async def test_cr050_max_steps_boundary(self, workspace: Path):
        """CR-050: 恰好 max_steps 时正确终止"""
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "loop",
                    trigger_patterns=[],
                    response_factory=lambda m, t: _tool_response(
                        "read_file", {"file_path": "main.md", "attempt": t}
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            max_steps=3,
        )

        events = await _collect_events(rt, "keep going")
        types = _event_types(events)
        assert AgentEventType.ERROR not in types
        assert AgentEventType.RESPONSE in types
        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "max_steps_exhausted"

    @pytest.mark.asyncio
    async def test_cr054_fast_sequential(self, workspace: Path):
        """CR-054: 快速连续对话"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        for i in range(10):
            events = await _collect_events(rt, f"message {i}")
            assert any(e.type in (AgentEventType.RESPONSE, AgentEventType.ERROR) for e in events)


# ============================================================================
# 6.7 多工具熔断协议完整性 (P0 regression)
# ============================================================================


class _ScriptedProvider:
    """Returns a scripted response per call index, ignoring message content.

    Lets a test drive multiple LLM turns within a single runtime turn so a
    circuit breaker can fire mid-batch after an earlier turn has pre-loaded a
    tool-call fingerprint.
    """

    model = "scripted"

    def __init__(self, responses: list):
        self._responses = responses
        self._index = 0

    async def chat(self, *, messages, tools, system_prompt=None):
        if self._index >= len(self._responses):
            return _text_response("done")
        response = self._responses[self._index]
        self._index += 1
        return response


def _read(file_path: str = "main.md", tool_id: str = "tu_read") -> ToolUseBlock:
    return ToolUseBlock(id=tool_id, name="read_file", input=json.dumps({"file_path": file_path}))


class TestMultiToolBudgetProtocol:
    """Every ToolUseBlock must have a matching ToolResultBlock, even when a
    total budget stops execution mid-batch. Otherwise the persisted session
    is protocol-invalid and the next resume fails with 'missing tool result'."""

    @pytest.mark.asyncio
    async def test_budget_mid_batch_supplements_skipped_tool_results(self, workspace: Path):
        """The first two reads consume the total budget. The next batch is
        stopped, and its never-executed calls receive synthetic results."""
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[_read(tool_id="r1"), _read(tool_id="r2")], stop_reason="tool_use"
                ),
                ProviderResponse(
                    blocks=[
                        _read(tool_id="r3"),
                        ToolUseBlock(
                            id="w1",
                            name="write_file",
                            input=json.dumps({"file_path": "out.md", "content": "x"}),
                        ),
                        ToolUseBlock(
                            id="g1",
                            name="grep_files",
                            input=json.dumps({"pattern": "Hello"}),
                        ),
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("final answer"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            max_tool_calls=2,
        )

        events = await _collect_events(rt, "read the file a few times then edit")

        call_ids = {e.data["id"] for e in events if e.type == AgentEventType.TOOL_CALL}
        results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        result_ids = {e.data["id"] for e in results}

        # Every emitted tool call must have exactly one matching result.
        assert call_ids == result_ids, f"calls {call_ids} != results {result_ids}"
        # The two never-executed tools are neutral skipped results, not failures.
        skipped = {e.data["id"] for e in results if e.data.get("status") == "skipped"}
        assert {"w1", "g1"} <= skipped, f"write/grep should be skipped, got {skipped}"

    @pytest.mark.asyncio
    async def test_persisted_history_pairs_every_tool_use_with_result(self, workspace: Path):
        """After a mid-batch budget stop, the session's persisted messages must
        pair every ToolUseBlock with a ToolResultBlock (protocol invariant)."""
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[_read(tool_id="r1"), _read(tool_id="r2")], stop_reason="tool_use"
                ),
                ProviderResponse(
                    blocks=[
                        _read(tool_id="r3"),
                        ToolUseBlock(
                            id="w1",
                            name="write_file",
                            input=json.dumps({"file_path": "out.md", "content": "x"}),
                        ),
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("final answer"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            max_tool_calls=2,
        )

        await _collect_events(rt, "read repeatedly then write")

        use_ids: set[str] = set()
        result_ids: set[str] = set()
        for message in session.messages:
            for block in message.blocks:
                if isinstance(block, ToolUseBlock):
                    use_ids.add(block.id)
                elif isinstance(block, ToolResultBlock):
                    result_ids.add(block.tool_use_id)

        assert use_ids == result_ids, f"ToolUse {use_ids} != ToolResult {result_ids}"

    @pytest.mark.asyncio
    async def test_tool_budget_exhaustion_finalizes_as_persisted_partial(self, workspace: Path):
        """RUN-01: budget exhaustion must finalize without admitting more tools."""
        calls = [
            ToolUseBlock(
                id=f"t{i}",
                name="noop",
                input=json.dumps({"value": i}),
            )
            for i in range(35)
        ]
        provider = _ScriptedProvider(
            [
                ProviderResponse(blocks=calls, stop_reason="tool_use"),
                _text_response("已完成部分操作，剩余验证因预算耗尽未执行。"),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)

        async def noop(_args):
            return ToolResult("ok")

        registry.register(
            "noop",
            "safe no-op",
            {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
            noop,
        )
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            max_tool_calls=32,
            soft_tool_calls=28,
        )

        events = await _collect_events(runtime, "perform a large batch")

        assert any(
            event.type == AgentEventType.RESPONSE and "预算耗尽" in event.data["text"]
            for event in events
        )
        assert not any(event.type == AgentEventType.ERROR for event in events)
        result_events = [event for event in events if event.type == AgentEventType.TOOL_RESULT]
        assert sum(event.data["status"] == "success" for event in result_events) == 32
        assert sum(event.data["status"] == "error" for event in result_events) == 1
        assert sum(event.data["status"] == "skipped" for event in result_events) == 2
        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "tool_budget_exhausted"
        assert session.meta.outcome["tool_counts"]["success"] == 32
        assert session.meta.outcome["tool_counts"]["skipped"] == 2

    @pytest.mark.asyncio
    async def test_finalizer_ignores_provider_tool_calls(self, workspace: Path):
        """The reserved finalizer cannot mutate state even if a provider ignores tools=[]."""
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(id="t1", name="noop", input="{}"),
                        ToolUseBlock(id="t2", name="noop", input="{}"),
                    ],
                    stop_reason="tool_use",
                ),
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(id="forbidden", name="noop", input="{}"),
                        TextBlock(text="One call completed; the remaining work is unfinished."),
                    ],
                    stop_reason="tool_use",
                ),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)
        executions: list[str] = []

        async def noop(_args):
            executions.append("executed")
            return ToolResult("ok")

        registry.register("noop", "no-op", {"type": "object"}, noop)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            max_tool_calls=1,
            soft_tool_calls=0,
        )

        events = await _collect_events(runtime, "run too much work")

        assert executions == ["executed"]
        assert not any(
            event.type == AgentEventType.TOOL_CALL and event.data["id"] == "forbidden"
            for event in events
        )
        assert session.meta.state == "PARTIAL"

    @pytest.mark.asyncio
    async def test_soft_budget_enters_draining_before_hard_stop(self, workspace: Path):
        class PromptCapturingProvider(_ScriptedProvider):
            def __init__(self, responses):
                super().__init__(responses)
                self.prompts: list[str] = []

            async def chat(self, *, messages, tools, system_prompt=None):
                self.prompts.append(system_prompt or "")
                return await super().chat(
                    messages=messages, tools=tools, system_prompt=system_prompt
                )

        provider = PromptCapturingProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(
                            id=f"t{i}",
                            name="noop",
                            input=json.dumps({"value": i}),
                        )
                        for i in range(3)
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("done"),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)

        async def noop(_args):
            return ToolResult("ok")

        registry.register("noop", "no-op", {"type": "object"}, noop)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            max_tool_calls=4,
            soft_tool_calls=3,
        )

        events = await _collect_events(runtime, "use the budget carefully")

        assert "Tool budget is low (1 calls remain)" in provider.prompts[-1]
        assert any(event.type == AgentEventType.RESPONSE for event in events)
        assert session.meta.state == "COMPLETE"

    @pytest.mark.asyncio
    async def test_soft_budget_technically_blocks_new_side_effects(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(
                            id=f"t{i}",
                            name="mutate",
                            input=json.dumps({"value": i}),
                        )
                        for i in range(3)
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("drained"),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)
        executed: list[int] = []

        async def mutate(args):
            executed.append(args["value"])
            return ToolResult("ok")

        registry.register(
            "mutate",
            "side effect",
            {"type": "object"},
            mutate,
            permission="workspace-write",
            effects={"filesystem_write"},
        )
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=True,
            max_tool_calls=4,
            soft_tool_calls=2,
        )

        events = await _collect_events(runtime, "mutate three times")

        assert executed == [0, 1]
        skipped = [
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT and event.data["status"] == "skipped"
        ]
        assert [event.data["id"] for event in skipped] == ["t2"]

    @pytest.mark.asyncio
    async def test_streamed_and_final_tool_blocks_merge_by_id(self, workspace: Path):
        class PartialStreamingProvider:
            model = "partial-stream"

            async def chat_stream(self, **_kwargs):
                first = ToolUseBlock(id="t1", name="noop", input='{"value": 1}')
                second = ToolUseBlock(id="t2", name="noop", input='{"value": 2}')
                yield first
                yield ProviderResponse(
                    blocks=[first, second],
                    stop_reason="tool_use",
                )

        registry = ToolRegistry(workspace_root=workspace)
        seen: list[int] = []

        async def noop(args):
            seen.append(args["value"])
            return ToolResult("ok")

        registry.register("noop", "no-op", {"type": "object"}, noop)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=PartialStreamingProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            max_steps=1,
        )

        events = await _collect_events(runtime, "stream two tool calls")

        assert seen == [1, 2]
        call_ids = [event.data["id"] for event in events if event.type == AgentEventType.TOOL_CALL]
        assert call_ids == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_tool_error_limit_counts_consecutive_failures(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(
                            id=f"t{i}",
                            name="flaky",
                            input=json.dumps({"value": value}),
                        )
                        for i, value in enumerate(
                            ["fail-1", "ok", "fail-2", "fail-3", "fail-4", "fail-5"]
                        )
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("recovered"),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)

        async def flaky(args):
            if args["value"] == "ok":
                return ToolResult("ok")
            return ToolResult("failed", is_error=True)

        registry.register("flaky", "flaky tool", {"type": "object"}, flaky)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
        )

        events = await _collect_events(runtime, "recover between failures")

        assert any(
            event.type == AgentEventType.RESPONSE and event.data["text"] == "recovered"
            for event in events
        )
        assert session.meta.state == "COMPLETE"

    @pytest.mark.asyncio
    async def test_resume_does_not_repeat_an_already_applied_write(
        self, workspace: Path, tmp_path: Path
    ):
        write = ToolUseBlock(
            id="write-1",
            name="write_file",
            input=json.dumps({"file_path": "draft.md", "content": "final"}),
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session_path = tmp_path / "resume.jsonl"
        first_session = Session(workspace=str(workspace))
        first_session._save_path = str(session_path)
        first = ConversationRuntime(
            provider=_ScriptedProvider(
                [ProviderResponse(blocks=[write], stop_reason="tool_use"), _text_response("done")]
            ),
            tool_registry=registry,
            permission_policy=policy,
            session=first_session,
            auto_approve=True,
        )
        await _collect_events(first, "write the draft")
        before_mtime = (workspace / "draft.md").stat().st_mtime_ns

        loaded = Session.load(session_path)
        resumed_registry = create_default_registry(workspace_root=workspace)
        resumed = ConversationRuntime(
            provider=_ScriptedProvider(
                [
                    ProviderResponse(
                        blocks=[
                            ToolUseBlock(
                                id="write-2",
                                name="write_file",
                                input=write.input,
                            )
                        ],
                        stop_reason="tool_use",
                    ),
                    _text_response("verified"),
                ]
            ),
            tool_registry=resumed_registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE,
                resumed_registry.permission_specs(),
            ),
            session=loaded,
            auto_approve=True,
        )

        events = await _collect_events(resumed, "continue unfinished verification")

        duplicate_result = next(
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT and event.data["id"] == "write-2"
        )
        assert duplicate_result.data["status"] == "no_change"
        assert not any(event.type == AgentEventType.CHECKPOINT for event in events)
        assert len(loaded.mutation_journal) == 1
        assert (workspace / "draft.md").stat().st_mtime_ns == before_mtime


# ============================================================================
# 6.8 读写读循环 & 重复调用 (F2 regression)
# ============================================================================


class TestReadEditReadCycle:
    """Legitimate repeated calls rely on idempotency and the total budget."""

    @pytest.mark.asyncio
    async def test_read_write_read_completes(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                ProviderResponse(blocks=[_read(tool_id="r1")], stop_reason="tool_use"),
                ProviderResponse(blocks=[_read(tool_id="r2")], stop_reason="tool_use"),
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(
                            id="w1",
                            name="write_file",
                            input=json.dumps({"file_path": "main.md", "content": "# Updated"}),
                        ),
                    ],
                    stop_reason="tool_use",
                ),
                ProviderResponse(blocks=[_read(tool_id="r3")], stop_reason="tool_use"),
                ProviderResponse(blocks=[_read(tool_id="r4")], stop_reason="tool_use"),
                _text_response("done"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "read edit read")
        assert not any(e.type == AgentEventType.ERROR for e in events)
        assert session.meta.state == "COMPLETE"

    @pytest.mark.asyncio
    async def test_repeated_identical_writes_are_idempotent(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(
                            id="w1",
                            name="write_file",
                            input=json.dumps({"file_path": "main.md", "content": "# Same"}),
                        ),
                        ToolUseBlock(
                            id="w2",
                            name="write_file",
                            input=json.dumps({"file_path": "main.md", "content": "# Same"}),
                        ),
                        ToolUseBlock(
                            id="w3",
                            name="write_file",
                            input=json.dumps({"file_path": "main.md", "content": "# Same"}),
                        ),
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("done"),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )

        events = await _collect_events(rt, "write same content three times")
        assert not any(e.type == AgentEventType.ERROR for e in events)
        assert session.meta.state == "COMPLETE"
        assert (workspace / "main.md").read_text(encoding="utf-8") == "# Same"
        results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        assert [e.data["status"] for e in results] == ["success", "no_change", "no_change"]


# ============================================================================
# 6.9 选区前后文注入 (F3 regression)
# ============================================================================


class TestSelectionContextInjection:
    """before_context/after_context must appear in the composed model message
    but must not alter the edit_scope write anchor."""

    def test_before_after_context_appear_in_message(self):
        from src.agent_v2.router import ChatRequestV2, SelectionContextV2, _compose_turn_message

        req = ChatRequestV2(
            message="polish this",
            selection=SelectionContextV2(
                file_path="draft/main.md",
                start_line=10,
                start_column=1,
                end_line=12,
                end_column=1,
                text="selected paragraph",
                before_context="previous paragraph here",
                after_context="next paragraph here",
            ),
        )
        msg = _compose_turn_message(req)
        assert "<selection_before>" in msg
        assert "previous paragraph here" in msg
        assert "<selection_after>" in msg
        assert "next paragraph here" in msg
        assert "READ-ONLY" in msg

    def test_edit_scope_ignores_context_fields(self, workspace: Path):
        """_apply_edit_scope must not use before_context/after_context."""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            edit_scope={
                "file_path": "main.md",
                "start_line": 1,
                "start_column": 1,
                "end_line": 1,
                "end_column": 14,
                "text": "# Hello World",
                "before_context": "ignored by scope guard",
                "after_context": "also ignored",
            },
        )
        tb = ToolUseBlock(
            id="tu_edit",
            name="str_replace",
            input=json.dumps(
                {
                    "file_path": "main.md",
                    "old_string": "# Hello World",
                    "new_string": "# Hello World!",
                }
            ),
        )
        assert rt._apply_edit_scope(tb, json.loads(tb.input)) is None


class TestAbortPropagation:
    @pytest.mark.asyncio
    async def test_abort_cancels_active_tool_and_persists_terminal_outcome(self, workspace: Path):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_tool(_args):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        provider = MockProvider(
            scenarios=[
                Scenario(
                    "slow",
                    trigger_patterns=["slow"],
                    response_factory=lambda _m, _t: _tool_response("slow_tool", {}),
                )
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)
        registry.register(
            "slow_tool",
            "Wait until cancelled",
            {"type": "object", "properties": {}},
            slow_tool,
        )
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
        )

        collector = asyncio.create_task(_collect_events(runtime, "slow"))
        await asyncio.wait_for(started.wait(), timeout=2)
        runtime.abort()
        events = await asyncio.wait_for(collector, timeout=2)

        assert cancelled.is_set()
        assert AgentEventType.ABORTED in _event_types(events)
        assert AgentEventType.DONE in _event_types(events)
        assert any(
            event.type == AgentEventType.TOOL_RESULT and event.data.get("status") == "skipped"
            for event in events
        )
        assert session.meta.state == "ABORTED"

    @pytest.mark.asyncio
    async def test_abort_cancels_blocked_provider_stream(self, workspace: Path):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class BlockingProvider:
            model = "blocking"

            def chat_stream(self, **_kwargs):
                async def stream():
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        cancelled.set()
                        raise
                    if False:
                        yield TextBlock(text="unreachable")

                return stream()

        registry = ToolRegistry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=BlockingProvider(),
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
        )

        collector = asyncio.create_task(_collect_events(runtime, "block"))
        await asyncio.wait_for(started.wait(), timeout=2)
        runtime.abort()
        events = await asyncio.wait_for(collector, timeout=2)

        assert cancelled.is_set()
        assert _event_types(events)[-2:] == [AgentEventType.ABORTED, AgentEventType.DONE]
        assert session.meta.state == "ABORTED"

    @pytest.mark.asyncio
    async def test_abort_cancels_pre_tool_hook_and_keeps_protocol_paired(self, workspace: Path):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocking_hook(_event):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return HookResult()

        hooks = HookRunner()
        hooks.register_callable("blocking", HookPoint.PRE_TOOL_USE, blocking_hook)
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "hook",
                    trigger_patterns=["hook"],
                    response_factory=lambda _m, _t: _tool_response("noop", {}),
                )
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)

        async def noop(_args):
            return ToolResult("must not run")

        registry.register("noop", "no-op", {"type": "object"}, noop)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            hook_runner=hooks,
        )

        collector = asyncio.create_task(_collect_events(runtime, "hook"))
        await asyncio.wait_for(started.wait(), timeout=2)
        runtime.abort()
        events = await asyncio.wait_for(collector, timeout=2)

        assert cancelled.is_set()
        assert session.meta.state == "ABORTED"
        assert any(
            event.type == AgentEventType.TOOL_RESULT and event.data["status"] == "skipped"
            for event in events
        )


class TestIndependentExecutionBudgets:
    @pytest.mark.asyncio
    async def test_research_budget_stops_duplicate_expansion_before_global_budget(
        self, workspace: Path
    ):
        provider = _ScriptedProvider(
            [
                _tool_response("web_search", {"query": "YOLO"}),
                _tool_response("web_search", {"query": "YOLOv2"}),
                _tool_response("web_search", {"query": "YOLOv3"}),
                _text_response("Research stopped before delivery."),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)

        async def web_search(args):
            return ToolResult(f"results for {args['query']}")

        registry.register(
            "web_search",
            "Search the web",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            web_search,
            permission="read-only",
            effects={"network"},
        )
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            max_research_calls=2,
        )

        events = await _collect_events(runtime, "research YOLO")

        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "research_budget_exhausted"
        partial = next(event for event in events if event.type == AgentEventType.RESPONSE)
        assert partial.data["partial"] is True
        assert partial.data["stop_code"] == "research_budget_exhausted"

    @pytest.mark.asyncio
    async def test_default_budget_allows_sixty_four_readonly_tools_and_final_response(
        self, workspace: Path
    ):
        class SixtyFourToolProvider:
            model = "budget-proof"

            def __init__(self):
                self.calls = 0

            async def chat(self, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return ProviderResponse(
                        blocks=[
                            ToolUseBlock(
                                id=f"inspect-{index}",
                                name="inspect_item",
                                input=json.dumps({"index": index}),
                            )
                            for index in range(64)
                        ],
                        stop_reason="tool_use",
                    )
                return _text_response("All 64 inspections completed.")

        provider = SixtyFourToolProvider()
        registry = ToolRegistry(workspace_root=workspace)

        async def inspect_item(args):
            return ToolResult(f"inspected {args['index']}")

        registry.register(
            "inspect_item",
            "Inspect one item",
            {
                "type": "object",
                "properties": {"index": {"type": "integer"}},
                "required": ["index"],
            },
            inspect_item,
            permission="read-only",
        )
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE,
                registry.permission_specs(),
            ),
            session=Session(workspace=str(workspace)),
        )

        events = await _collect_events(runtime, "inspect 64 items")

        successful = [
            event
            for event in events
            if event.type == AgentEventType.TOOL_RESULT and not event.data.get("is_error")
        ]
        assert len(successful) == 64
        assert provider.calls == 2
        assert runtime.session.meta.state == "COMPLETE"
        assert any(
            event.type == AgentEventType.RESPONSE
            and event.data.get("text") == "All 64 inspections completed."
            for event in events
        )

    @pytest.mark.asyncio
    async def test_model_call_budget_includes_followup_and_uses_local_finalizer(
        self, workspace: Path
    ):
        class CountingProvider:
            model = "counting"

            def __init__(self):
                self.calls = 0

            async def chat(self, **_kwargs):
                self.calls += 1
                return ProviderResponse(
                    blocks=[ToolUseBlock(id="n1", name="noop", input="{}")],
                    stop_reason="tool_use",
                )

        provider = CountingProvider()
        registry = ToolRegistry(workspace_root=workspace)

        async def noop(_args):
            return ToolResult("ok")

        registry.register("noop", "no-op", {"type": "object"}, noop)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            max_model_calls=1,
        )

        events = await _collect_events(runtime, "do one step")

        assert provider.calls == 1
        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "model_call_budget_exhausted"
        partial = next(event for event in events if event.type == AgentEventType.RESPONSE)
        assert partial.data["partial"] is True
        assert partial.data["stop_code"] == "model_call_budget_exhausted"
        assert partial.data["tool_counts"]["success"] == 1
        assert "Changed files:" not in partial.data["text"]

    @pytest.mark.asyncio
    async def test_mutation_attempt_budget_stops_second_write(self, workspace: Path):
        provider = _ScriptedProvider(
            [
                ProviderResponse(
                    blocks=[
                        ToolUseBlock(id="m1", name="mutate", input='{"value": 1}'),
                        ToolUseBlock(id="m2", name="mutate", input='{"value": 2}'),
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("Only the admitted mutation completed."),
            ]
        )
        registry = ToolRegistry(workspace_root=workspace)
        executed: list[int] = []

        async def mutate(args):
            executed.append(args["value"])
            return ToolResult("ok")

        registry.register(
            "mutate",
            "mutating operation",
            {"type": "object"},
            mutate,
            permission="workspace-write",
            effects={"filesystem_write"},
        )
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            auto_approve=True,
            max_mutation_attempts=1,
        )

        events = await _collect_events(runtime, "mutate twice")

        assert executed == [1]
        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "mutation_budget_exhausted"
        partial = next(event for event in events if event.type == AgentEventType.RESPONSE)
        assert partial.data["text"] == "Only the admitted mutation completed."
        assert partial.data["partial"] is True
        assert partial.data["stop_code"] == "mutation_budget_exhausted"

    @pytest.mark.asyncio
    async def test_active_time_budget_cancels_provider_and_persists_partial(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        cancelled = asyncio.Event()

        class SlowProvider:
            model = "slow"

            async def chat(self, **_kwargs):
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        monkeypatch.setenv("SCHOLAR_AGENT_STREAM", "0")
        registry = ToolRegistry(workspace_root=workspace)
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=SlowProvider(),
            tool_registry=registry,
            permission_policy=policy_from_registry(
                PermissionMode.WORKSPACE_WRITE, registry.permission_specs()
            ),
            session=session,
            max_active_seconds=0.02,
        )

        events = await asyncio.wait_for(
            _collect_events(runtime, "wait forever"),
            timeout=1,
        )

        assert cancelled.is_set()
        assert session.meta.state == "PARTIAL"
        assert session.meta.outcome["stop_code"] == "active_time_exhausted"
        assert _event_types(events)[-1] == AgentEventType.DONE
