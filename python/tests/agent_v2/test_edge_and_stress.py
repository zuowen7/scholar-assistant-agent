"""Edge cases and stress tests for all new modules.

Covers boundary conditions, malformed inputs, empty states, large data,
concurrent access, and error propagation.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

from src.agent_v2.types import (
    Message, MessageRole, TextBlock, ToolUseBlock, ToolResultBlock, TokenUsage,
)


def _user(text: str) -> Message:
    return Message(role=MessageRole.USER, blocks=[TextBlock(text=text)])


def _asst(text: str) -> Message:
    return Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text=text)])


# ============================================================================
# Bash Validation — edge cases
# ============================================================================

class TestBashValidationEdge:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.bash_validation import (
            validate_command, classify_command, is_read_only_command,
            extract_first_command, check_destructive, ValidationResult,
        )
        self.validate_command = validate_command
        self.classify = classify_command
        self.is_ro = is_read_only_command
        self.extract = extract_first_command
        self.check_destructive = check_destructive
        self.Result = ValidationResult

    def test_empty_command(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path
        result = self.validate_command("", PermissionMode.READ_ONLY, Path("/ws"))
        assert result.is_allowed

    def test_whitespace_only_command(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path
        result = self.validate_command("   \t  ", PermissionMode.READ_ONLY, Path("/ws"))
        assert result.is_allowed

    def test_unicode_command(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path
        # Unicode in paths should not crash
        result = self.validate_command("cat 你好世界.txt", PermissionMode.READ_ONLY, Path("/ws"))
        assert result.is_allowed

    def test_nested_sudo(self):
        from src.agent_v2.runtime.bash_validation import extract_sudo_inner
        result = extract_sudo_inner("sudo -u root -n echo hello")
        assert result == "echo hello"

    def test_many_env_vars(self):
        result = self.extract("A=1 B=2 C=3 D=4 E=5 python script.py")
        assert result == "python"

    def test_nested_quotes_in_env(self):
        result = self.extract('FOO="hello world" BAR=\'baz qux\' ls')
        assert result == "ls"

    def test_command_with_backslash(self):
        result = self.extract("echo hello\\ world")
        assert result == "echo"

    def test_destructive_fork_bomb_variant(self):
        result = self.check_destructive(":(){ :|:& };:")
        assert result.is_warn

    def test_destructive_dd_with_of(self):
        result = self.check_destructive("dd if=/dev/zero of=/dev/sda bs=1M count=100")
        assert result.is_warn

    def test_read_only_rejects_pipe(self):
        assert not self.is_ro("echo hello | grep hi")

    def test_read_only_rejects_dollar_paren(self):
        assert not self.is_ro("echo $(whoami)")

    def test_read_only_allows_realpath(self):
        assert self.is_ro("realpath ./src")

    def test_read_only_allows_tree(self):
        assert self.is_ro("tree -L 2")

    def test_classify_with_full_path(self):
        from src.agent_v2.runtime.bash_validation import CommandIntent
        assert self.classify("/usr/bin/git status") == CommandIntent.READ_ONLY
        assert self.classify("/usr/local/bin/python app.py") == CommandIntent.UNKNOWN

    def test_validate_command_allows_in_full_access(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path
        # Everything allowed in full access mode
        result = self.validate_command("rm -rf /", PermissionMode.DANGER_FULL_ACCESS, Path("/ws"))
        assert result.is_allowed or result.is_warn  # may still warn about destructive

    def test_validate_command_blocks_git_push_in_readonly(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path
        result = self.validate_command("git push origin main", PermissionMode.READ_ONLY, Path("/ws"))
        assert result.is_blocked


# ============================================================================
# Git Context — edge cases
# ============================================================================

class TestGitContextEdge:

    def test_detect_on_nonexistent_path(self):
        from src.agent_v2.runtime.git_context import GitContext
        from pathlib import Path
        assert GitContext.detect(Path("/nonexistent/path/xyz")) is None

    def test_detect_on_file_not_dir(self, tmp_path):
        from src.agent_v2.runtime.git_context import GitContext
        from pathlib import Path
        f = tmp_path / "file.txt"
        f.write_text("hello")
        # GitContext.detect on a file should return None gracefully
        try:
            result = GitContext.detect(f)
            assert result is None
        except (NotADirectoryError, OSError):
            pass  # subprocess can't cwd to a file — expected

    def test_render_empty_context(self):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext(branch=None, recent_commits=[], staged_files=[])
        assert ctx.render() == ""

    def test_render_very_long_branch_name(self):
        from src.agent_v2.runtime.git_context import GitContext
        branch = "feature/" + "a" * 200
        ctx = GitContext(branch=branch, recent_commits=[], staged_files=[])
        rendered = ctx.render()
        assert branch in rendered


# ============================================================================
# Hooks — edge cases
# ============================================================================

class TestHooksEdge:

    @pytest.mark.asyncio
    async def test_hook_with_malformed_json_stdout(self):
        from src.agent_v2.hooks import HookRunner, HookPoint, HookEvent, HookDefinition
        runner = HookRunner()
        # Output that looks like JSON start but is invalid
        runner.register(HookDefinition(name="bad", hook_point=HookPoint.POST_TOOL_USE,
                                        command='echo {invalid json', priority=10))
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.POST_TOOL_USE, event)
        assert result.decision.value == "allow"

    @pytest.mark.asyncio
    async def test_hook_with_very_large_input(self):
        from src.agent_v2.hooks import HookRunner, HookPoint, HookEvent, HookResult, HookDecision
        runner = HookRunner()
        def log(event: HookEvent) -> HookResult:
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("log", HookPoint.PRE_TOOL_USE, log, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test",
                          tool_input="x" * 1_000_000)
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_abort_signal_after_completion(self):
        from src.agent_v2.hooks import HookRunner, HookPoint, HookEvent, HookAbortSignal
        runner = HookRunner()
        signal = runner.create_abort_signal()
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision.value == "allow"
        # Abort after completion should not affect past results
        signal.abort()
        assert signal.is_aborted()

    @pytest.mark.asyncio
    async def test_many_concurrent_abort_signals(self):
        from src.agent_v2.hooks import HookAbortSignal
        signals = [HookAbortSignal() for _ in range(100)]
        for s in signals[:50]:
            s.abort()
        assert sum(1 for s in signals if s.is_aborted()) == 50


# ============================================================================
# Trident — edge cases
# ============================================================================

class TestTridentEdge:

    def test_supersede_with_no_messages(self):
        from src.agent_v2.runtime.trident import stage1_supersede
        kept, count = stage1_supersede([])
        assert kept == []
        assert count == 0

    def test_collapse_with_all_tool_messages(self):
        from src.agent_v2.runtime.trident import stage2_collapse
        messages = [
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t1", name="read_file", input='{}')]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t1", tool_name="read_file", output="content")]),
        ] * 5
        result, chains, collapsed = stage2_collapse(messages, threshold=4)
        assert chains == 0

    def test_cluster_with_empty_messages(self):
        from src.agent_v2.runtime.trident import stage3_cluster
        result, clusters, clustered = stage3_cluster([], min_size=3, threshold=0.6)
        assert clusters == 0

    def test_supersede_with_mixed_case_paths(self):
        """File paths with different cases are treated as different files."""
        from src.agent_v2.runtime.trident import stage1_supersede
        messages = [
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t1", name="read_file", input='{"file_path": "File.txt"}')]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t1", tool_name="read_file", output="content")]),
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t2", name="write_file", input='{"file_path": "file.txt", "content": "x"}')]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t2", tool_name="write_file", output="ok")]),
        ]
        kept, count = stage1_supersede(messages)
        # Different paths → no superseding
        assert count == 0 or kept == messages  # depends on case sensitivity


# ============================================================================
# Recovery — edge cases
# ============================================================================

class TestRecoveryEdge:

    def test_all_scenarios_recoverable(self):
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        ctx = RecoveryContext()
        for scenario in FailureScenario.all():
            result = attempt_recovery(scenario, ctx)
            assert result.is_recovered, f"{scenario.value} should be recoverable on first attempt"

    def test_all_scenarios_escalate_on_retry(self):
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        for scenario in FailureScenario.all():
            ctx = RecoveryContext()
            attempt_recovery(scenario, ctx)
            r2 = attempt_recovery(scenario, ctx)
            assert r2.is_escalation_required, f"{scenario.value} should escalate on 2nd attempt"

    def test_fail_at_step_beyond_length(self):
        """fail_at_step beyond step count should still succeed."""
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario, attempt_recovery
        ctx = RecoveryContext().with_fail_at_step(999)
        result = attempt_recovery(FailureScenario.TRUST_PROMPT_UNRESOLVED, ctx)
        assert result.is_recovered

    def test_status_report_for_never_attempted(self):
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario
        ctx = RecoveryContext()
        report = ctx.status_report(FailureScenario.STALE_BRANCH)
        assert not report.attempted
        assert report.state is None


# ============================================================================
# Session — edge cases
# ============================================================================

class TestSessionEdge:

    def test_fork_with_no_messages(self):
        from src.agent_v2.runtime.session import Session
        session = Session()
        forked = session.fork()
        assert len(forked.messages) == 0
        assert forked.fork_meta is not None

    def test_fork_preserves_workspace(self, tmp_path):
        from src.agent_v2.runtime.session import Session
        session = Session(workspace=str(tmp_path), model="test")
        forked = session.fork()
        assert forked.meta.workspace == str(tmp_path)
        assert forked.meta.model == "test"

    def test_session_control_state_transitions(self):
        from src.agent_v2.runtime.session_control import SessionControl, SessionState
        ctrl = SessionControl()
        # Active → Paused → Active → Aborted
        ctrl.pause()
        assert ctrl.state == SessionState.PAUSED
        ctrl.resume()
        assert ctrl.state == SessionState.ACTIVE
        ctrl.abort()
        assert ctrl.state == SessionState.ABORTED
        # Can't resume from aborted
        ctrl.resume()
        assert ctrl.state == SessionState.ABORTED


# ============================================================================
# LSP — edge cases
# ============================================================================

class TestLspEdge:

    def test_dispatch_to_disconnected_server(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspAction
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        result = reg.dispatch("python", LspAction.HOVER, path="main.py")
        assert "error" in result

    def test_dispatch_to_nonexistent_server(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspAction
        reg = LspRegistry()
        result = reg.dispatch("unknown", LspAction.DIAGNOSTICS, path="x")
        assert "error" in result

    def test_multiple_registrations_overwrite(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        reg.register("python", {"command": "pyright"})
        assert len(reg.list_servers()) == 1


# ============================================================================
# PromptCache — edge cases
# ============================================================================

class TestPromptCacheEdge:

    def test_zero_tokens(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        tracker.record_hit(tokens_saved=0)
        assert tracker.cache_hits == 1
        assert tracker.tokens_saved == 0

    def test_large_tokens(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        tracker.record_hit(tokens_saved=10_000_000)
        assert tracker.tokens_saved == 10_000_000

    def test_many_events(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        for i in range(1000):
            tracker.record_hit(100)
            tracker.record_miss(50)
        assert tracker.cache_hits == 1000
        assert tracker.cache_misses == 1000
        assert len(tracker.events) == 2000


# ============================================================================
# Policy Engine — edge cases
# ============================================================================

class TestPolicyEngineEdge:

    def test_empty_context(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("r1", PolicyCondition(key="x", value=True), PolicyAction.RETRY))
        assert engine.evaluate({}) == []

    def test_threshold_with_non_numeric(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("r1", PolicyCondition(key="x", threshold=10), PolicyAction.ESCALATE))
        assert engine.evaluate({"x": "hello"}) == []

    def test_many_rules(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        for i in range(100):
            engine.add_rule(PolicyRule(f"r{i}", PolicyCondition(key="x", value=True),
                                       PolicyAction.LOG, priority=i))
        actions = engine.evaluate({"x": True})
        assert len(actions) == 100
        # First action should be lowest priority number
        assert actions[0].priority == 0


# ============================================================================
# Sandbox — edge cases
# ============================================================================

class TestSandboxEdge:

    def test_truncate_empty_string(self):
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(max_output_bytes=10)
        assert config.truncate_output("") == ""

    def test_truncate_exact_boundary(self):
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(max_output_bytes=10)
        output = "x" * 10
        # Exactly at boundary, should not truncate
        assert config.truncate_output(output) == output

    def test_clean_env_without_flag(self):
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(clear_env_vars=False)
        env = {"HTTP_PROXY": "http://evil", "PATH": "/usr/bin"}
        assert config.clean_env(env) == env  # unchanged

    def test_truncate_multibyte_boundary(self):
        """UTF-8 multi-byte char spanning the max_output_bytes boundary."""
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(max_output_bytes=5)
        output = "a" * 4 + "字"  # 6 bytes total, the CJK char is 3 bytes in UTF-8
        result = config.truncate_output(output)
        assert "[output truncated]" in result

    def test_clean_env_blocked_vars(self):
        from src.agent_v2.runtime.sandbox import SandboxConfig
        config = SandboxConfig(clear_env_vars=True)
        env = {"HTTP_PROXY": "http://evil", "PATH": "/usr/bin", "HOME": "/home"}
        cleaned = config.clean_env(env)
        assert "HTTP_PROXY" not in cleaned
        assert "PATH" in cleaned

    def test_sandbox_result_blocked_property(self):
        from src.agent_v2.runtime.sandbox import SandboxResult
        r = SandboxResult(allowed=False, reason="cwd outside workspace")
        assert r.blocked
        assert not r.allowed


# ============================================================================
# Policy Engine — additional edge cases
# ============================================================================

class TestPolicyEngineEdgeMore:

    def test_boolean_value_in_context(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("r1", PolicyCondition(key="flag", value=True), PolicyAction.LOG))
        assert len(engine.evaluate({"flag": True})) == 1
        assert len(engine.evaluate({"flag": False})) == 0

    def test_none_in_context(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("r1", PolicyCondition(key="x", value=None), PolicyAction.LOG))
        # context has key "x" with value None → matches
        assert len(engine.evaluate({"x": None})) == 1

    def test_threshold_exact_match(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("r1", PolicyCondition(key="score", threshold=10), PolicyAction.ESCALATE))
        assert len(engine.evaluate({"score": 10})) == 1

    def test_threshold_below(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("r1", PolicyCondition(key="score", threshold=10), PolicyAction.ESCALATE))
        assert len(engine.evaluate({"score": 9})) == 0

    def test_duplicate_priorities(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("a", PolicyCondition(key="x", value=True), PolicyAction.LOG, priority=10))
        engine.add_rule(PolicyRule("b", PolicyCondition(key="x", value=True), PolicyAction.RETRY, priority=10))
        actions = engine.evaluate({"x": True})
        assert len(actions) == 2  # both match, order preserved

    def test_multiple_conditions_conflicting(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        engine = PolicyEngine()
        engine.add_rule(PolicyRule("log", PolicyCondition(key="x", value=True), PolicyAction.LOG, priority=1))
        engine.add_rule(PolicyRule("abort", PolicyCondition(key="x", value=True), PolicyAction.ABORT, priority=2))
        actions = engine.evaluate({"x": True})
        assert actions[0].action == PolicyAction.LOG  # lower priority first


# ============================================================================
# PromptCache — additional edge cases
# ============================================================================

class TestPromptCacheEdgeMore:

    def test_hit_rate_all_misses(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        tracker.record_miss(100)
        tracker.record_miss(200)
        assert tracker.hit_rate == 0.0
        assert tracker.cache_hits == 0
        assert tracker.cache_misses == 2

    def test_hit_rate_empty(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        assert tracker.hit_rate == 0.0

    def test_summary_rounds_hit_rate(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        tracker.record_hit(100)
        tracker.record_miss(100)
        s = tracker.summary()
        assert s["cache_hits"] == 1
        assert s["cache_misses"] == 1
        assert s["hit_rate"] == 0.5
        assert s["tokens_saved"] == 100

    def test_cache_writes_tracked(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker
        tracker = PromptCacheTracker()
        tracker.record_miss(500)
        assert tracker.cache_writes == 500


# ============================================================================
# LSP — additional edge cases
# ============================================================================

class TestLspEdgeMore:

    def test_from_str_all_variants(self):
        from src.agent_v2.runtime.lsp_client import LspAction
        assert LspAction.from_str("goto_definition") == LspAction.DEFINITION
        assert LspAction.from_str("find_references") == LspAction.REFERENCES
        assert LspAction.from_str("completions") == LspAction.COMPLETION
        assert LspAction.from_str("document_symbols") == LspAction.SYMBOLS
        assert LspAction.from_str("formatting") == LspAction.FORMAT
        assert LspAction.from_str("nonexistent_action") is None

    def test_state_transition_disconnected_to_ready(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspClientState, LspAction
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        assert reg.get_state("python") == LspClientState.DISCONNECTED
        reg.connect("python")
        assert reg.get_state("python") == LspClientState.CONNECTING
        reg.mark_ready("python")
        assert reg.get_state("python") == LspClientState.READY

    def test_state_transition_to_error(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspClientState
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        reg.mark_error("python", "connection refused")
        assert reg.get_state("python") == LspClientState.ERROR
        assert reg.get_last_error("python") == "connection refused"

    def test_connect_nonexistent_language(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspClientState
        reg = LspRegistry()
        reg.connect("unknown")  # should not crash
        assert reg.get_state("unknown") == LspClientState.DISCONNECTED

    def test_get_state_unknown(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspClientState
        reg = LspRegistry()
        assert reg.get_state("unknown") == LspClientState.DISCONNECTED

    def test_unregister_clears_error(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspClientState
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        reg.mark_error("python", "timeout")
        reg.unregister("python")
        assert reg.get_state("python") == LspClientState.DISCONNECTED
        assert reg.get_last_error("python") is None

    def test_dispatch_when_connecting(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspAction
        reg = LspRegistry()
        reg.register("python", {"command": "pylsp"})
        reg.connect("python")
        result = reg.dispatch("python", LspAction.HOVER, path="x.py")
        assert "error" in result
        assert "not ready" in result["error"]

    def test_from_string_alias(self):
        from src.agent_v2.runtime.lsp_client import LspAction
        assert LspAction.from_string("hover") == LspAction.HOVER


# ============================================================================
# Trident — additional edge cases
# ============================================================================

class TestTridentEdgeMore:

    def test_stage2_empty_messages(self):
        from src.agent_v2.runtime.trident import stage2_collapse
        result, chains, collapsed = stage2_collapse([])
        assert result == []
        assert chains == 0

    def test_stage2_threshold_zero(self):
        from src.agent_v2.runtime.trident import stage2_collapse
        from src.agent_v2.types import Message, MessageRole, TextBlock
        msgs = [
            Message(role=MessageRole.USER, blocks=[TextBlock(text="ok")]),
            Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="got it")]),
        ]
        result, chains, collapsed = stage2_collapse(msgs, threshold=0)
        assert collapsed == 2

    def test_stage2_below_threshold_passthrough(self):
        from src.agent_v2.runtime.trident import stage2_collapse
        from src.agent_v2.types import Message, MessageRole, TextBlock
        msgs = [
            Message(role=MessageRole.USER, blocks=[TextBlock(text="ok")]),
            Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="got it")]),
        ]
        result, chains, collapsed = stage2_collapse(msgs, threshold=5)
        assert collapsed == 0
        assert len(result) == 2

    def test_stage3_all_different_texts(self):
        from src.agent_v2.runtime.trident import stage3_cluster
        from src.agent_v2.types import Message, MessageRole, TextBlock
        msgs = [
            Message(role=MessageRole.USER, blocks=[TextBlock(text="apple banana cherry")]),
            Message(role=MessageRole.USER, blocks=[TextBlock(text="dog elephant frog")]),
            Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="goat horse iguana")]),
        ]
        result, clusters, clustered = stage3_cluster(msgs, min_size=2, threshold=0.5)
        assert clusters == 0

    def test_stage3_similar_texts_cluster(self):
        from src.agent_v2.runtime.trident import stage3_cluster
        from src.agent_v2.types import Message, MessageRole, TextBlock
        msgs = [
            Message(role=MessageRole.USER, blocks=[TextBlock(text="apple banana cherry")]),
            Message(role=MessageRole.USER, blocks=[TextBlock(text="apple banana cherry date")]),
            Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="apple banana date elderberry")]),
        ]
        result, clusters, clustered = stage3_cluster(msgs, min_size=2, threshold=0.6)
        assert clusters > 0

    def test_stage1_supersede_multiple_writes_same_file(self):
        from src.agent_v2.runtime.trident import stage1_supersede
        import json
        from src.agent_v2.types import Message, MessageRole, ToolUseBlock, ToolResultBlock
        msgs = [
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t1", name="write_file", input=json.dumps({"file_path": "f.txt"}))]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t1", tool_name="write_file", output="ok")]),
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t2", name="write_file", input=json.dumps({"file_path": "f.txt"}))]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t2", tool_name="write_file", output="ok")]),
        ]
        kept, count = stage1_supersede(msgs)
        assert count == 2  # first write + its tool result superseded
        assert len(kept) == 2  # only last write + its result remain

    def test_stage1_read_not_superseded(self):
        from src.agent_v2.runtime.trident import stage1_supersede
        import json
        from src.agent_v2.types import Message, MessageRole, ToolUseBlock, ToolResultBlock
        msgs = [
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t1", name="read_file", input=json.dumps({"file_path": "f.txt"}))]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t1", tool_name="read_file", output="v1")]),
            Message(role=MessageRole.ASSISTANT, blocks=[ToolUseBlock(id="t2", name="read_file", input=json.dumps({"file_path": "f.txt"}))]),
            Message(role=MessageRole.TOOL, blocks=[ToolResultBlock(tool_use_id="t2", tool_name="read_file", output="v2")]),
        ]
        kept, count = stage1_supersede(msgs)
        assert count == 0  # reads are never superseded


# ============================================================================
# Recovery — additional edge cases
# ============================================================================

class TestRecoveryEdgeMore:

    def test_from_worker_failure_unknown_kind(self):
        from src.agent_v2.runtime.recovery import FailureScenario
        s = FailureScenario.from_worker_failure("some_random_error")
        assert s == FailureScenario.PROVIDER_FAILURE

    def test_recovery_result_partial_properties(self):
        from src.agent_v2.runtime.recovery import RecoveryResult
        r = RecoveryResult.partial_recovery(recovered=["step1"], remaining=["step2"])
        assert r.is_partial_recovery
        assert not r.is_recovered
        assert not r.is_escalation_required

    def test_recovery_result_escalation_properties(self):
        from src.agent_v2.runtime.recovery import RecoveryResult
        r = RecoveryResult.escalation_required("out of retries")
        assert r.is_escalation_required
        assert not r.is_recovered


# ============================================================================
# Bash Validation — additional edge cases
# ============================================================================

class TestBashValidationEdgeMore:

    def test_extract_sudo_no_inner_command(self):
        from src.agent_v2.runtime.bash_validation import extract_sudo_inner
        assert extract_sudo_inner("sudo -u root") == ""

    def test_extract_first_command_no_command_after_env(self):
        from src.agent_v2.runtime.bash_validation import extract_first_command
        result = extract_first_command("A=1 B=2")
        assert result == ""

    def test_extract_first_command_with_path(self):
        from src.agent_v2.runtime.bash_validation import extract_first_command
        result = extract_first_command("/usr/local/bin/python app.py")
        assert result == "python"

    def test_destructive_pattern_mkfs(self):
        from src.agent_v2.runtime.bash_validation import check_destructive
        result = check_destructive("mkfs.ext4 /dev/sda1")
        assert result.is_warn

    def test_destructive_shred(self):
        from src.agent_v2.runtime.bash_validation import check_destructive
        result = check_destructive("shred -f secret.txt")
        assert result.is_warn

    def test_validate_mode_workspace_write_outside_workspace(self):
        from src.agent_v2.runtime.bash_validation import validate_mode
        from src.agent_v2.runtime.permissions import PermissionMode
        result = validate_mode("rm /etc/config", PermissionMode.WORKSPACE_WRITE)
        assert result.is_warn

    def test_classify_unknown_command(self):
        from src.agent_v2.runtime.bash_validation import classify_command, CommandIntent
        assert classify_command("my_custom_tool_xyz") == CommandIntent.UNKNOWN

    def test_is_read_only_non_ascii_command(self):
        from src.agent_v2.runtime.bash_validation import is_read_only_command
        # Unknown non-ASCII command should not crash
        result = is_read_only_command("文件管理器")
        assert not result


# ============================================================================
# Session / SessionStore — additional edge cases
# ============================================================================

class TestSessionEdgeMore:

    def test_fork_generates_new_session_id(self):
        from src.agent_v2.runtime.session import Session
        session = Session()
        forked = session.fork()
        assert forked.session_id != session.session_id

    def test_fork_meta_parent_session_id(self):
        from src.agent_v2.runtime.session import Session
        session = Session()
        forked = session.fork()
        assert forked.fork_meta is not None
        assert forked.fork_meta.parent_session_id == session.session_id

    def test_session_store_fingerprint_deterministic(self, tmp_path):
        from src.agent_v2.runtime.session_control import SessionStore
        s1 = SessionStore(tmp_path)
        s2 = SessionStore(tmp_path)
        assert s1.sessions_dir() == s2.sessions_dir()

    def test_session_store_delete_nonexistent(self, tmp_path):
        from src.agent_v2.runtime.session_control import SessionStore
        store = SessionStore(tmp_path)
        assert not store.delete("nonexistent-session-id")


# ============================================================================
# Git Context — additional edge cases
# ============================================================================

class TestGitContextEdgeMore:

    def test_detect_on_tmp_path(self, tmp_path):
        from src.agent_v2.runtime.git_context import GitContext
        # tmp_path is not a git repo
        assert GitContext.detect(tmp_path) is None

    def test_render_with_only_branch(self):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext(branch="main", recent_commits=[], staged_files=[])
        rendered = ctx.render()
        assert "Git branch: main" in rendered
        assert "Recent commits" not in rendered

    def test_render_with_commits_no_branch(self):
        from src.agent_v2.runtime.git_context import GitContext, GitCommitEntry
        ctx = GitContext(branch=None, recent_commits=[
            GitCommitEntry(hash="abc1234", subject="fix: bug")
        ], staged_files=[])
        rendered = ctx.render()
        assert "abc1234" in rendered
        assert "Git branch" not in rendered


# ============================================================================
# ToolRegistry — bash validation integration edge cases
# ============================================================================

class TestRegistryBashValidationEdge:

    def test_permission_policy_check_default(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from src.agent_v2.tools.registry import ToolRegistry
        reg = ToolRegistry(workspace_root=None)
        mode, = reg._permission_policy_check("ls")
        assert mode == PermissionMode.WORKSPACE_WRITE

    def test_permission_policy_check_after_set(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from src.agent_v2.tools.registry import ToolRegistry
        reg = ToolRegistry(workspace_root=None)
        reg.set_permission_mode(PermissionMode.READ_ONLY)
        mode, = reg._permission_policy_check("ls")
        assert mode == PermissionMode.READ_ONLY

    def test_set_permission_mode_all_values(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from src.agent_v2.tools.registry import ToolRegistry
        for pm in PermissionMode:
            reg = ToolRegistry(workspace_root=None)
            reg.set_permission_mode(pm)
            mode, = reg._permission_policy_check("test")
            assert mode == pm

    def test_check_workspace_escape_no_root(self):
        from src.agent_v2.tools.registry import ToolRegistry
        reg = ToolRegistry(workspace_root=None)
        assert not reg.check_workspace_escape("../etc/passwd")
        assert not reg.check_workspace_escape("/etc/passwd")

    def test_check_workspace_escape_with_root(self, tmp_path):
        from src.agent_v2.tools.registry import ToolRegistry
        reg = ToolRegistry(workspace_root=tmp_path)
        safe = tmp_path / "file.txt"
        assert not reg.check_workspace_escape(str(safe))

    def test_resolve_path_defaults_to_cwd(self):
        from src.agent_v2.tools.registry import ToolRegistry
        reg = ToolRegistry(workspace_root=None)
        # "." should resolve to current working directory
        resolved = reg._resolve_path(".")
        assert resolved.is_absolute()

    def test_resolve_path_with_workspace_root(self, tmp_path):
        from src.agent_v2.tools.registry import ToolRegistry
        reg = ToolRegistry(workspace_root=tmp_path)
        resolved = reg._resolve_path("subdir/file.txt")
        assert (tmp_path / "subdir" / "file.txt") == resolved


# ============================================================================
# Hooks — HookRunResult edge cases
# ============================================================================

class TestHookRunResultEdgeMore:

    def test_is_allowed_and_is_denied_mutually_exclusive(self):
        from src.agent_v2.hooks import HookRunResult, HookDecision
        r = HookRunResult(decision=HookDecision.ALLOW)
        assert r.is_allowed and not r.is_denied
        r2 = HookRunResult(decision=HookDecision.DENY)
        assert r2.is_denied and not r2.is_allowed

    def test_messages_default_empty(self):
        from src.agent_v2.hooks import HookRunResult, HookDecision
        r = HookRunResult(decision=HookDecision.ALLOW)
        assert r.messages == []

    def test_messages_accumulate(self):
        from src.agent_v2.hooks import HookRunResult, HookDecision
        r = HookRunResult(decision=HookDecision.ALLOW, messages=["msg1", "msg2"])
        assert len(r.messages) == 2


# ============================================================================
# Session — save/load with fork meta
# ============================================================================

class TestSessionSaveLoadForkEdge:

    def test_save_load_preserves_fork_meta(self, tmp_path):
        from src.agent_v2.runtime.session import Session
        session = Session()
        session.append(_user("fork test"))
        forked = session.fork(branch_name="feature/edge")
        path = tmp_path / "fork.jsonl"
        forked.save(path)
        loaded = Session.load(path)
        assert loaded.fork_meta is not None
        assert loaded.fork_meta.parent_session_id == session.session_id
        assert loaded.fork_meta.branch_name == "feature/edge"

    def test_save_load_without_fork_meta(self, tmp_path):
        from src.agent_v2.runtime.session import Session
        session = Session()
        session.append(_user("plain"))
        path = tmp_path / "plain.jsonl"
        session.save(path)
        loaded = Session.load(path)
        assert loaded.fork_meta is None
        assert len(loaded.messages) == 1
