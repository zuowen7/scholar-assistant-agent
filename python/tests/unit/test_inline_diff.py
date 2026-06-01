"""Inline Diff Approval — TDD 测试用例。

覆盖：
- A1: SecurityGate — 所有 str_replace/write_file 统一 force_approval=True
- A2: Session — _build_approval_preview + await_approval SSE 预览数据
- A3: PromptBuilder — inline diff + export 工具指导
"""
from __future__ import annotations

import pytest

from src.agent.security_gate import SecurityGate, ToolRiskLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gate():
    return SecurityGate()


@pytest.fixture
def gate_with_workspace(tmp_path):
    (tmp_path / "draft.md").write_text("existing content")
    return SecurityGate(workspace_root=str(tmp_path))


# ---------------------------------------------------------------------------
# A1: SecurityGate — force_approval for ALL file edits
# ---------------------------------------------------------------------------


class TestInlineDiffForceApproval:
    """所有 str_replace / write_file 必须返回 force_approval=True。"""

    def test_str_replace_small_change(self, gate):
        r = gate.classify("str_replace", {
            "file_path": "paper.md",
            "old_string": "hello",
            "new_string": "world",
        })
        assert r.force_approval is True
        assert r.needs_approval is True
        assert r.risk == ToolRiskLevel.DESTRUCTIVE

    def test_str_replace_empty_args(self, gate):
        r = gate.classify("str_replace", {})
        assert r.force_approval is True

    def test_str_replace_large_delete(self, gate):
        old = "\n".join(f"line {i}" for i in range(80))
        r = gate.classify("str_replace", {
            "old_string": old, "new_string": "replaced",
        })
        assert r.force_approval is True

    def test_write_file_new_file(self, gate):
        r = gate.classify("write_file", {
            "file_path": "new.md", "content": "hello", "must_not_exist": True,
        })
        assert r.force_approval is True
        assert r.needs_approval is True

    def test_write_file_new_no_flag(self, gate_with_workspace):
        r = gate_with_workspace.classify("write_file", {
            "file_path": "brand_new.md", "content": "hello",
        })
        assert r.force_approval is True

    def test_write_file_overwrite(self, gate_with_workspace):
        r = gate_with_workspace.classify("write_file", {
            "file_path": "draft.md", "content": "new",
        })
        assert r.force_approval is True

    def test_write_file_large_new(self, gate):
        r = gate.classify("write_file", {
            "file_path": "big.md", "content": "x" * 15000,
        })
        assert r.force_approval is True

    def test_non_file_tools_unaffected(self, gate):
        """非文件工具不受影响。"""
        r1 = gate.classify("run_command", {"command": "ls"})
        assert r1.risk == ToolRiskLevel.SAFE
        r2 = gate.classify("read_file", {"file_path": "a.md"})
        assert r2.risk == ToolRiskLevel.SAFE


# ---------------------------------------------------------------------------
# A2a: _build_approval_preview 纯函数测试
# ---------------------------------------------------------------------------


class TestBuildApprovalPreview:
    """_build_approval_preview 为 str_replace/write_file 生成预览数据。"""

    def test_str_replace_preview(self):
        from src.agent.session import _build_approval_preview
        p = _build_approval_preview("str_replace", {
            "file_path": "paper.md",
            "old_string": "old text",
            "new_string": "new text",
        })
        assert p is not None
        assert p["type"] == "str_replace"
        assert p["file_path"] == "paper.md"
        assert p["old_text"] == "old text"
        assert p["new_text"] == "new text"

    def test_str_replace_line_counts(self):
        from src.agent.session import _build_approval_preview
        p = _build_approval_preview("str_replace", {
            "file_path": "a.md",
            "old_string": "line1\nline2\nline3",
            "new_string": "new1\nnew2",
        })
        assert p["old_line_count"] == 3
        assert p["new_line_count"] == 2

    def test_write_file_preview_no_old_text(self):
        from src.agent.session import _build_approval_preview
        p = _build_approval_preview("write_file", {
            "file_path": "out.md", "content": "full content",
        })
        assert p is not None
        assert p["type"] == "write_file"
        assert p["file_path"] == "out.md"
        assert "new_text" in p
        assert "old_text" not in p

    def test_non_file_tool_returns_none(self):
        from src.agent.session import _build_approval_preview
        assert _build_approval_preview("run_command", {"command": "ls"}) is None
        assert _build_approval_preview("git_op", {"operation": "commit"}) is None
        assert _build_approval_preview("read_file", {"file_path": "a.md"}) is None

    def test_long_text_truncated_to_800(self):
        from src.agent.session import _build_approval_preview
        long = "x" * 2000
        p = _build_approval_preview("str_replace", {
            "file_path": "big.md", "old_string": long, "new_string": long,
        })
        assert len(p["old_text"]) <= 800
        assert len(p["new_text"]) <= 800

    def test_empty_args(self):
        from src.agent.session import _build_approval_preview
        p = _build_approval_preview("str_replace", {})
        assert p is not None
        assert p["old_text"] == ""
        assert p["new_text"] == ""


# ---------------------------------------------------------------------------
# A2b: await_approval SSE 事件集成测试
# ---------------------------------------------------------------------------


class TestApprovalPreviewInSSE:
    """await_approval SSE 事件应包含 preview 元数据。"""

    @pytest.mark.asyncio
    async def test_str_replace_approval_has_preview(self):
        from src.agent.agent import AgentLoop, StepResult
        from src.agent.models import EVT_AWAIT_APPROVAL, AgentEvent, Message, ToolCall
        from src.agent.session import AgentSession, SessionConfig

        agent = AgentLoop(ollama_base_url="http://localhost:99999", model="test")

        async def fake_step(messages, *, step_num=1, max_steps=20, execute_tools=True):
            tc = ToolCall(
                id="tc_1", name="str_replace",
                arguments={"file_path": "paper.md", "old_string": "hello", "new_string": "world"},
            )
            messages.append(Message(role="assistant", content="", tool_calls=[tc]))
            return StepResult(
                events=[AgentEvent(type="tool_call", content="", metadata={"tool_name": "str_replace"})],
                tool_calls=[tc], tool_results=[],
            )

        async def fake_exec(tc, query):
            return "replaced"

        agent.step = fake_step
        agent._execute_single_tool = fake_exec

        s = AgentSession(
            agent=agent,
            config=SessionConfig(auto_approve=True, approval_timeout=0.01),
        )
        events = [ev async for ev in s.drive("replace hello")]

        approval = next(ev for ev in events if ev.type == EVT_AWAIT_APPROVAL)
        assert "preview" in approval.metadata
        assert approval.metadata["preview"]["type"] == "str_replace"
        assert approval.metadata["preview"]["old_text"] == "hello"
        assert approval.metadata["preview"]["new_text"] == "world"

    @pytest.mark.asyncio
    async def test_write_file_approval_has_preview(self):
        from src.agent.agent import AgentLoop, StepResult
        from src.agent.models import EVT_AWAIT_APPROVAL, AgentEvent, Message, ToolCall
        from src.agent.session import AgentSession, SessionConfig

        agent = AgentLoop(ollama_base_url="http://localhost:99999", model="test")

        async def fake_step(messages, *, step_num=1, max_steps=20, execute_tools=True):
            tc = ToolCall(
                id="tc_2", name="write_file",
                arguments={"file_path": "out.md", "content": "exported content"},
            )
            messages.append(Message(role="assistant", content="", tool_calls=[tc]))
            return StepResult(
                events=[AgentEvent(type="tool_call", content="", metadata={"tool_name": "write_file"})],
                tool_calls=[tc], tool_results=[],
            )

        async def fake_exec(tc, query):
            return "written"

        agent.step = fake_step
        agent._execute_single_tool = fake_exec

        s = AgentSession(
            agent=agent,
            config=SessionConfig(auto_approve=True, approval_timeout=0.01),
        )
        events = [ev async for ev in s.drive("write")]

        approval = next(ev for ev in events if ev.type == EVT_AWAIT_APPROVAL)
        assert "preview" in approval.metadata
        assert approval.metadata["preview"]["type"] == "write_file"
        assert approval.metadata["preview"]["file_path"] == "out.md"

    @pytest.mark.asyncio
    async def test_non_file_approval_no_preview(self):
        from src.agent.agent import AgentLoop, StepResult
        from src.agent.models import EVT_AWAIT_APPROVAL, AgentEvent, Message, ToolCall
        from src.agent.session import AgentSession, SessionConfig

        agent = AgentLoop(ollama_base_url="http://localhost:99999", model="test")

        async def fake_step(messages, *, step_num=1, max_steps=20, execute_tools=True):
            tc = ToolCall(
                id="tc_3", name="shell_exec",
                arguments={"code": "print(1)"},
            )
            messages.append(Message(role="assistant", content="", tool_calls=[tc]))
            return StepResult(
                events=[AgentEvent(type="tool_call", content="", metadata={"tool_name": "shell_exec"})],
                tool_calls=[tc], tool_results=[],
            )

        async def fake_exec(tc, query):
            return "1"

        agent.step = fake_step
        agent._execute_single_tool = fake_exec

        s = AgentSession(
            agent=agent,
            config=SessionConfig(auto_approve=False, approval_timeout=0.01),
        )
        events = [ev async for ev in s.drive("run code")]

        approval = next((ev for ev in events if ev.type == EVT_AWAIT_APPROVAL), None)
        if approval:
            assert "preview" not in approval.metadata or approval.metadata.get("preview") is None


# ---------------------------------------------------------------------------
# A3: PromptBuilder — inline diff + export guidance
# ---------------------------------------------------------------------------


class TestInlineDiffToolGuide:
    """默认工具指导应包含 inline diff 审批 + workspace 外导出引导。"""

    def test_default_guide_mentions_diff_review(self):
        from src.agent.prompt_builder import PromptBuilder
        builder = PromptBuilder()
        guide = builder._get_model_guide("unknown-model")
        assert any(kw in guide for kw in ["diff", "Diff", "内联", "预览", "accept", "reject", "接受"])

    def test_default_guide_mentions_export(self):
        from src.agent.prompt_builder import PromptBuilder
        builder = PromptBuilder()
        guide = builder._get_model_guide("unknown-model")
        assert any(kw in guide for kw in ["export", "Export", "导出", "桌面", "desktop"])

    def test_known_model_guide_still_has_specific_content(self):
        from src.agent.prompt_builder import PromptBuilder
        builder = PromptBuilder()
        guide = builder._get_model_guide("qwen3:8b")
        assert "严禁在同一轮对话中多次调用同一个工具" in guide

    def test_default_guide_mentions_str_replace_preference(self):
        """应鼓励优先用 str_replace 而非 write_file（更好的 diff 体验）。"""
        from src.agent.prompt_builder import PromptBuilder
        builder = PromptBuilder()
        guide = builder._get_model_guide("unknown-model")
        assert any(kw in guide for kw in ["str_replace", "小而精确", "精准替换"])

    def test_default_guide_mentions_run_command_for_pip(self):
        """应引导 Agent 用 run_command 而非 shell_exec 来装包。"""
        from src.agent.prompt_builder import PromptBuilder
        builder = PromptBuilder()
        guide = builder._get_model_guide("unknown-model")
        assert "run_command" in guide
        assert "pip" in guide
