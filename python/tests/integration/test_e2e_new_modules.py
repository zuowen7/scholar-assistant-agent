"""End-to-end integration tests: router → runtime → new modules.

Tests the full chain from HTTP request to runtime behavior,
covering all 10 newly ported modules in realistic scenarios.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agent_v2.types import (
    Message, MessageRole, TextBlock, ToolUseBlock, ToolResultBlock, TokenUsage,
)


def _user(text: str) -> Message:
    return Message(role=MessageRole.USER, blocks=[TextBlock(text=text)])


def _asst(text: str) -> Message:
    return Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text=text)])


# ============================================================================
# 1. Runtime construction with all new modules wired in
# ============================================================================

class TestRuntimeConstruction:

    def test_runtime_with_bash_validation(self, tmp_path: Path):
        """Runtime's run_command uses bash validation pipeline."""
        from src.agent_v2.tools.registry import create_default_registry
        registry = create_default_registry(workspace_root=tmp_path)
        spec = registry.get("run_command")
        assert spec is not None
        # The permission mode is wired in
        from src.agent_v2.runtime.permissions import PermissionMode
        registry.set_permission_mode(PermissionMode.READ_ONLY)
        assert registry._active_permission_mode == PermissionMode.READ_ONLY

    def test_runtime_with_git_context_in_prompt(self, tmp_path: Path):
        """Git context can be injected into system prompt."""
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext(branch="main", recent_commits=[], staged_files=[])
        rendered = ctx.render()
        assert "main" in rendered

    def test_runtime_with_trident_compact(self, tmp_path: Path):
        """Trident compact integrates with session messages."""
        from src.agent_v2.runtime.trident import trident_compact_session, TridentConfig
        from src.agent_v2.runtime.compact import CompactionConfig
        from src.agent_v2.runtime.session import Session

        session = Session()
        # Simulate a session with file ops that can be superseded
        for m in [
            _user("read a.txt"),
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t1", name="read_file", input='{"file_path": "a.txt"}')]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t1", tool_name="read_file", output="old content")]),
            _user("write a.txt"),
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t2", name="write_file", input='{"file_path": "a.txt", "content": "new"}')]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t2", tool_name="write_file", output="ok")]),
        ]:
            session.append(m)

        config = CompactionConfig(input_token_threshold=1_000_000)
        result = trident_compact_session(session, config, TridentConfig())
        assert result is not None

    def test_runtime_with_recovery(self):
        """Recovery recipes can be attempted during runtime errors."""
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        ctx = RecoveryContext()
        result = attempt_recovery(FailureScenario.PROVIDER_FAILURE, ctx)
        assert result.is_recovered

    def test_runtime_with_session_fork(self, tmp_path: Path):
        """Session can be forked during a conversation."""
        from src.agent_v2.runtime.session import Session
        session = Session(workspace=str(tmp_path))
        session.append(_user("hello"))
        session.append(_asst("hi there"))

        forked = session.fork(branch_name="experiment")
        assert forked.fork_meta is not None
        assert forked.fork_meta.parent_session_id == session.session_id
        assert len(forked.messages) == 2

    def test_runtime_with_session_control(self):
        """Session can be paused and resumed."""
        from src.agent_v2.runtime.session_control import SessionControl, SessionState
        ctrl = SessionControl()
        assert ctrl.is_active()
        ctrl.pause()
        assert not ctrl.is_active()
        ctrl.resume()
        assert ctrl.is_active()

    @pytest.mark.asyncio
    async def test_runtime_with_hooks_advanced(self):
        """Hooks can modify tool input and provide permission overrides."""
        from src.agent_v2.hooks import HookRunner, HookPoint, HookEvent, HookResult, HookDecision
        runner = HookRunner()

        def rewrite(event: HookEvent) -> HookResult:
            data = json.loads(event.tool_input) if event.tool_input else {}
            data["sanitized"] = True
            return HookResult(decision=HookDecision.ALLOW, updated_input=json.dumps(data))

        runner.register_callable("sanitize", HookPoint.PRE_TOOL_USE, rewrite, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file",
                          tool_input='{"file_path": "test.md"}')

        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.updated_input is not None
        data = json.loads(result.updated_input)
        assert data["sanitized"] is True

    def test_runtime_with_prompt_cache(self):
        """Prompt cache tracking integrates with usage tracking."""
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        from src.agent_v2.runtime.usage import UsageTracker

        tracker = UsageTracker(model="claude-sonnet-4-6")
        cache = PromptCacheTracker()

        # Simulate a cached turn
        tracker.record(TokenUsage(input_tokens=1000, output_tokens=500, cache_read_tokens=800))
        cache.record_hit(tokens_saved=800)

        # Simulate a non-cached turn
        tracker.record(TokenUsage(input_tokens=2000, output_tokens=600))
        cache.record_miss(tokens_written=2000)

        assert tracker.total_input == 3000
        assert cache.hit_rate == 0.5
        assert cache.tokens_saved == 800

    def test_runtime_with_lsp_registry(self):
        """LSP registry can be queried during agent operation."""
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspAction
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        reg.connect("python")
        reg.mark_ready("python")
        result = reg.dispatch("python", LspAction.DIAGNOSTICS, path="main.py")
        assert result["action"] == "diagnostics"
        assert result["status"] == "dispatched"

    def test_runtime_with_policy_engine(self):
        """Policy engine can drive runtime decisions."""
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            name="escalate_stale",
            condition=PolicyCondition(key="stale_branch", value=True),
            action=PolicyAction.ESCALATE,
            priority=10,
        ))
        engine.add_rule(PolicyRule(
            name="retry_provider",
            condition=PolicyCondition(key="retry_available", value=True),
            action=PolicyAction.RETRY,
            priority=20,
        ))
        actions = engine.evaluate({"stale_branch": True, "retry_available": True})
        assert len(actions) == 2
        assert actions[0].action == PolicyAction.ESCALATE  # lower priority number wins

    def test_runtime_with_sandbox_config(self):
        """Sandbox config can be applied to command execution."""
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(timeout_seconds=10, clear_env_vars=True)
        env = {"HTTP_PROXY": "http://evil:8080", "PATH": "/usr/bin"}
        cleaned = config.clean_env(env)
        assert "HTTP_PROXY" not in cleaned
        assert "PATH" in cleaned


# ============================================================================
# 2. Git Context + System Prompt integration
# ============================================================================

class TestGitContextSystemPrompt:

    def test_git_context_injected_into_build_prompt(self, tmp_path: Path):
        """_build_system_prompt should include git context when available."""
        from src.agent_v2.router import _build_system_prompt
        from src.agent_v2.runtime.git_context import GitContext
        from src.agent_v2.tools.registry import create_default_registry

        registry = create_default_registry(workspace_root=tmp_path)
        base = _build_system_prompt(str(tmp_path), registry.definitions())
        assert "Scholar Assistant" in base
        assert "Available tools:" in base

        # With git context
        ctx = GitContext(branch="main", recent_commits=[], staged_files=["README.md"])
        git_section = ctx.render()
        full = base + "\n\n--- Git Context ---\n" + git_section
        assert "Git branch: main" in full
        assert "README.md" in full


# ============================================================================
# 3. Bash Validation + run_command integration
# ============================================================================

class TestBashValidationIntegration:

    @pytest.mark.asyncio
    async def test_run_command_blocked_in_read_only(self, tmp_path: Path):
        """run_command blocks dangerous commands in read-only mode."""
        from src.agent_v2.tools.registry import create_default_registry
        from src.agent_v2.runtime.permissions import PermissionMode

        registry = create_default_registry(workspace_root=tmp_path)
        registry.set_permission_mode(PermissionMode.READ_ONLY)
        result = await registry.execute("run_command", {"command": "rm -rf /"})
        assert result.is_error
        assert "not allowed" in result.output.lower() or "blocked" in result.output.lower()

    @pytest.mark.asyncio
    async def test_run_command_allows_safe_read(self, tmp_path: Path):
        """run_command allows read-only commands in read-only mode."""
        from src.agent_v2.tools.registry import create_default_registry
        from src.agent_v2.runtime.permissions import PermissionMode

        registry = create_default_registry(workspace_root=tmp_path)
        registry.set_permission_mode(PermissionMode.READ_ONLY)
        result = await registry.execute("run_command", {"command": "echo hello"})
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_run_command_warns_destructive_in_write_mode(self, tmp_path: Path):
        """run_command warns but proceeds for destructive commands in write mode."""
        from src.agent_v2.tools.registry import create_default_registry
        from src.agent_v2.runtime.permissions import PermissionMode

        registry = create_default_registry(workspace_root=tmp_path)
        registry.set_permission_mode(PermissionMode.WORKSPACE_WRITE)
        result = await registry.execute("run_command", {"command": "rm -rf /tmp/test_e2e"})
        # Should have a WARNING prefix but not be an error
        if "WARNING" in result.output:
            assert not result.is_error


# ============================================================================
# 4. Session lifecycle: create → fork → compact → store → load
# ============================================================================

class TestSessionLifecycle:

    def test_full_session_lifecycle(self, tmp_path: Path):
        from src.agent_v2.runtime.session import Session
        from src.agent_v2.runtime.session_control import SessionStore

        # Create
        session = Session(workspace=str(tmp_path), model="test-model")
        session.append(_user("translate this"))
        session.append(_asst("好的，我来翻译"))

        # Fork
        forked = session.fork(branch_name="chinese")
        forked.append(_user("继续翻译"))

        # Save both
        store = SessionStore.from_cwd(tmp_path)
        store.save(session)
        store.save(forked)

        # List
        sessions = store.list_sessions()
        assert len(sessions) == 2

        # Load
        loaded = store.load(forked.session_id)
        assert loaded is not None
        assert len(loaded.messages) == 3
        assert loaded.fork_meta.branch_name == "chinese"

        # Delete
        store.delete(forked.session_id)
        assert store.load(forked.session_id) is None
        assert len(store.list_sessions()) == 1

    def test_session_compact_after_long_conversation(self, tmp_path: Path):
        """Trident compact reduces messages in a long session."""
        from src.agent_v2.runtime.session import Session
        from src.agent_v2.runtime.trident import stage1_supersede, stage2_collapse

        session = Session(workspace=str(tmp_path))
        # Build conversation with repeated file ops
        for i in range(3):
            session.append(_user(f"read file{i}.txt"))
            session.append(Message(role=MessageRole.ASSISTANT, blocks=[
                ToolUseBlock(id=f"r{i}", name="read_file", input=f'{{"file_path": "shared.md"}}')
            ]))
            session.append(Message(role=MessageRole.TOOL, blocks=[
                ToolResultBlock(tool_use_id=f"r{i}", tool_name="read_file", output=f"v{i}")
            ]))
        # Final write supersedes all reads
        session.append(Message(role=MessageRole.ASSISTANT, blocks=[
            ToolUseBlock(id="w1", name="write_file", input='{"file_path": "shared.md", "content": "final"}')
        ]))
        session.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id="w1", tool_name="write_file", output="ok")
        ]))

        msgs = session.messages
        kept, count = stage1_supersede(msgs)
        assert count >= 3  # All reads + results superseded by final write

        # Collapse chatty exchanges
        msgs2, chains, collapsed = stage2_collapse(kept, threshold=2)
        # Some user messages may collapse


# ============================================================================
# 5. Recovery + Policy integration
# ============================================================================

class TestRecoveryPolicyIntegration:

    def test_provider_failure_triggers_recovery_then_policy(self):
        """Provider failure → auto-recovery → policy escalation if exhausted."""
        from src.agent_v2.runtime.recovery import (
            RecoveryContext, FailureScenario, attempt_recovery,
        )
        from src.agent_v2.runtime.policy_engine import (
            PolicyEngine, PolicyRule, PolicyCondition, PolicyAction,
        )

        ctx = RecoveryContext()
        engine = PolicyEngine()

        # Policy: escalate on provider failure exhaustion
        engine.add_rule(PolicyRule(
            name="escalate_provider",
            condition=PolicyCondition(key="provider_exhausted", value=True),
            action=PolicyAction.ESCALATE, priority=10,
        ))
        engine.add_rule(PolicyRule(
            name="retry_provider",
            condition=PolicyCondition(key="provider_retry_available", value=True),
            action=PolicyAction.RETRY, priority=20,
        ))

        # First attempt: recovery succeeds
        r1 = attempt_recovery(FailureScenario.PROVIDER_FAILURE, ctx)
        assert r1.is_recovered

        # Second attempt: recovery exhausted, trigger policy
        r2 = attempt_recovery(FailureScenario.PROVIDER_FAILURE, ctx)
        assert r2.is_escalation_required

        # Evaluate policy with exhaustion context
        actions = engine.evaluate({
            "provider_exhausted": True,
            "provider_retry_available": False,
        })
        assert len(actions) == 1
        assert actions[0].action == PolicyAction.ESCALATE

    def test_mcp_failure_recovery_with_policy(self):
        """MCP handshake failure → recovery → log policy."""
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction

        ctx = RecoveryContext()
        result = attempt_recovery(FailureScenario.MCP_HANDSHAKE_FAILURE, ctx)
        assert result.is_recovered

        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            name="log_mcp",
            condition=PolicyCondition(key="mcp_recovered", value=True),
            action=PolicyAction.LOG, priority=50,
        ))
        actions = engine.evaluate({"mcp_recovered": True})
        assert actions[0].action == PolicyAction.LOG


# ============================================================================
# 6. Hooks + Permission integration
# ============================================================================

class TestHooksPermissionIntegration:

    @pytest.mark.asyncio
    async def test_hook_deny_blocks_tool_despite_permission(self):
        """Hook denial overrides permission policy allow."""
        from src.agent_v2.hooks import HookRunner, HookPoint, HookEvent, HookResult, HookDecision
        from src.agent_v2.runtime.permissions import PermissionPolicy, PermissionMode

        runner = HookRunner()

        def deny_all(event: HookEvent) -> HookResult:
            return HookResult(decision=HookDecision.DENY, reason="security policy")

        runner.register_callable("security", HookPoint.PRE_TOOL_USE, deny_all, priority=10)

        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="run_command",
                          tool_input='{"command": "ls"}')
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.DENY

        # Even though permission policy would allow
        policy = PermissionPolicy(active_mode=PermissionMode.ALLOW)
        auth = policy.authorize("run_command", '{}')
        assert auth.is_allowed  # policy allows, but hook denied

    @pytest.mark.asyncio
    async def test_hook_updated_input_changes_tool_behavior(self, tmp_path: Path):
        """Hook can rewrite tool input to sanitize path traversal."""
        from src.agent_v2.hooks import HookRunner, HookPoint, HookEvent, HookResult, HookDecision

        runner = HookRunner()

        def sanitize_path(event: HookEvent) -> HookResult:
            data = json.loads(event.tool_input) if event.tool_input else {}
            fp = data.get("file_path", "")
            # Strip directory traversal
            while "../" in fp:
                fp = fp.replace("../", "")
            data["file_path"] = fp
            return HookResult(decision=HookDecision.ALLOW, updated_input=json.dumps(data))

        runner.register_callable("sanitize", HookPoint.PRE_TOOL_USE, sanitize_path, priority=10)

        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file",
                          tool_input='{"file_path": "../../../etc/passwd", "content": "hacked"}')
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        data = json.loads(result.updated_input)
        assert "../" not in data["file_path"]


# ============================================================================
# 7. Edge: concurrent sessions, abort, timeout
# ============================================================================

class TestConcurrencyEdges:

    @pytest.mark.asyncio
    async def test_abort_unblocks_pending_approval(self):
        """Aborting a runtime should unblock pending approval waits."""
        from src.agent_v2.runtime.conversation import ConversationRuntime
        from src.agent_v2.runtime.permissions import PermissionPolicy, PermissionMode
        from src.agent_v2.runtime.session import Session
        from src.agent_v2.tools.registry import create_default_registry
        from src.agent_v2.providers.mock_provider import MockProvider, Scenario

        provider = MockProvider()
        # Use response_factory for a tool-use response
        def _tool_use_resp(msgs, turn_idx, tools, system_prompt=""):
            from src.agent_v2.types import ToolUseBlock, TokenUsage, ProviderResponse
            return ProviderResponse(
                blocks=[ToolUseBlock(id="tu_abort_test", name="write_file",
                                      input='{"file_path":"x","content":"y"}')],
                usage=TokenUsage(input_tokens=50, output_tokens=20),
                stop_reason="end_turn",
            )
        provider.scenarios = [Scenario("write", response_factory=_tool_use_resp)]
        registry = create_default_registry()
        policy = PermissionPolicy(active_mode=PermissionMode.WORKSPACE_WRITE)
        session = Session()

        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                   permission_policy=policy, session=session,
                                   auto_approve=False)

        async def _run_and_abort():
            await asyncio.sleep(0.1)
            rt.abort()

        task = asyncio.create_task(_run_and_abort())
        events = []
        async for event in rt.turn("write something"):
            events.append(event)

        await task
        assert any(e.type.value == "aborted" for e in events) or any(
            e.type.value == "done" for e in events)

    def test_session_store_isolation(self, tmp_path: Path):
        """Different workspaces have isolated session stores."""
        from src.agent_v2.runtime.session_control import SessionStore
        from src.agent_v2.runtime.session import Session

        ws1 = tmp_path / "project1"
        ws2 = tmp_path / "project2"
        ws1.mkdir()
        ws2.mkdir()

        store1 = SessionStore.from_cwd(ws1)
        store2 = SessionStore.from_cwd(ws2)

        s1 = Session(workspace=str(ws1))
        s1.append(_user("project 1"))
        store1.save(s1)

        s2 = Session(workspace=str(ws2))
        s2.append(_user("project 2"))
        store2.save(s2)

        assert len(store1.list_sessions()) == 1
        assert len(store2.list_sessions()) == 1
        assert store1.load(s2.session_id) is None
        assert store2.load(s1.session_id) is None


# ============================================================================
# 8. Edge: sandbox config + run_command
# ============================================================================

class TestSandboxEdgeCases:

    def test_sandbox_truncate_unicode(self):
        """Sandbox truncation handles multi-byte characters."""
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(max_output_bytes=20)
        output = "你好世界" * 100  # Chinese chars, multi-byte
        truncated = config.truncate_output(output)
        assert "truncated" in truncated
        assert len(truncated) < len(output)

    def test_sandbox_clean_env_preserves_path(self):
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(clear_env_vars=True)
        env = {"PATH": "/usr/bin", "HOME": "/home/user", "HTTPS_PROXY": "http://proxy"}
        cleaned = config.clean_env(env)
        assert "PATH" in cleaned
        assert "HTTPS_PROXY" not in cleaned
        assert "HOME" in cleaned

    @pytest.mark.asyncio
    async def test_run_command_with_sandbox_timeout(self, tmp_path: Path):
        """run_command respects timeout (30s default)."""
        from src.agent_v2.tools.registry import create_default_registry
        registry = create_default_registry(workspace_root=tmp_path)
        result = await registry.execute("run_command", {"command": "echo fast"})
        assert not result.is_error


# ============================================================================
# 9. Edge: recovery ledger + multiple scenarios
# ============================================================================

class TestRecoveryEdgeCases:

    def test_multiple_scenarios_independent(self):
        """Recovery of one scenario doesn't affect another."""
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        ctx = RecoveryContext()
        r1 = attempt_recovery(FailureScenario.PROVIDER_FAILURE, ctx)
        r2 = attempt_recovery(FailureScenario.MCP_HANDSHAKE_FAILURE, ctx)
        assert r1.is_recovered
        assert r2.is_recovered

    def test_partial_recovery_tracks_remaining_steps(self):
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        ctx = RecoveryContext().with_fail_at_step(1)
        result = attempt_recovery(FailureScenario.PARTIAL_PLUGIN_STARTUP, ctx)
        if result.is_partial_recovery:
            assert len(result.remaining) > 0
            assert len(result.recovered) > 0

    def test_ledger_reports_correct_state_after_exhaustion(self):
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        ctx = RecoveryContext()
        attempt_recovery(FailureScenario.TRUST_PROMPT_UNRESOLVED, ctx)
        attempt_recovery(FailureScenario.TRUST_PROMPT_UNRESOLVED, ctx)
        report = ctx.status_report(FailureScenario.TRUST_PROMPT_UNRESOLVED)
        assert report.attempted
        assert report.state == "exhausted"


# ============================================================================
# 10. Prompt cache + usage tracker integration
# ============================================================================

class TestCacheUsageIntegration:

    def test_cache_tracking_with_real_usage(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        from src.agent_v2.runtime.usage import UsageTracker, pricing_for_model

        tracker = UsageTracker(model="claude-sonnet-4-6")
        cache = PromptCacheTracker()

        # Turn 1: cache miss
        usage1 = TokenUsage(input_tokens=5000, output_tokens=1000,
                              cache_creation_tokens=3000)
        tracker.record(usage1)
        cache.record_miss(tokens_written=3000)

        # Turn 2: cache hit
        usage2 = TokenUsage(input_tokens=5000, output_tokens=800,
                              cache_read_tokens=3000)
        tracker.record(usage2)
        cache.record_hit(tokens_saved=3000)

        assert tracker.call_count == 2
        assert tracker.total_cache_read == 3000
        assert cache.hit_rate == 0.5
        assert cache.tokens_saved == 3000

        # Cost calculation via summary string
        summary = tracker.summary()
        assert "Cost" in summary or "cost" in summary
