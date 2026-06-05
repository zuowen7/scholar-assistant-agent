"""TDD tests for LSP Client Registry, PromptCache Event, Sandbox, and Policy Engine.

Combined test file for 4 smaller modules (Tasks #7-10).
"""
from __future__ import annotations

import pytest


# ============================================================================
# Task #7: LSP Client Registry
# ============================================================================

class TestLspClientRegistry:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.lsp_client import LspRegistry, LspAction, LspClientState
        self.Registry = LspRegistry
        self.Action = LspAction
        self.State = LspClientState

    def test_register_and_list(self):
        reg = self.Registry()
        reg.register("python", {"command": "pylsp", "args": []})
        servers = reg.list_servers()
        assert len(servers) == 1
        assert "python" in servers

    def test_state_transitions(self):
        reg = self.Registry()
        reg.register("python", {"command": "pylsp"})
        assert reg.get_state("python") == self.State.DISCONNECTED
        reg.connect("python")
        assert reg.get_state("python") == self.State.CONNECTING
        reg.mark_ready("python")
        assert reg.get_state("python") == self.State.READY

    def test_state_error(self):
        reg = self.Registry()
        reg.register("python", {"command": "pylsp"})
        reg.connect("python")
        reg.mark_error("python", "crashed")
        assert reg.get_state("python") == self.State.ERROR
        assert reg.get_last_error("python") == "crashed"

    def test_unregister(self):
        reg = self.Registry()
        reg.register("python", {"command": "pylsp"})
        reg.unregister("python")
        assert "python" not in reg.list_servers()

    def test_unknown_server_state(self):
        reg = self.Registry()
        assert reg.get_state("unknown") == self.State.DISCONNECTED

    def test_action_from_string(self):
        assert self.Action.from_str("diagnostics") == self.Action.DIAGNOSTICS
        assert self.Action.from_str("hover") == self.Action.HOVER
        assert self.Action.from_str("definition") == self.Action.DEFINITION
        assert self.Action.from_str("references") == self.Action.REFERENCES
        assert self.Action.from_string("completion") == self.Action.COMPLETION
        assert self.Action.from_string("symbols") == self.Action.SYMBOLS
        assert self.Action.from_string("format") == self.Action.FORMAT
        assert self.Action.from_string("unknown") is None

    def test_dispatch_diagnostics(self):
        reg = self.Registry()
        reg.register("python", {"command": "pylsp"})
        reg.connect("python")
        reg.mark_ready("python")
        result = reg.dispatch("python", self.Action.DIAGNOSTICS, path="main.py")
        assert result is not None
        assert result["action"] == "diagnostics"


# ============================================================================
# Task #8: PromptCache Event
# ============================================================================

class TestPromptCacheEvent:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.prompt_cache import PromptCacheTracker, CacheEvent
        self.Tracker = PromptCacheTracker
        self.CacheEvent = CacheEvent

    def test_initial_stats_zero(self):
        tracker = self.Tracker()
        assert tracker.cache_hits == 0
        assert tracker.cache_misses == 0
        assert tracker.tokens_saved == 0

    def test_record_cache_hit(self):
        tracker = self.Tracker()
        tracker.record_hit(tokens_saved=500)
        assert tracker.cache_hits == 1
        assert tracker.tokens_saved == 500

    def test_record_cache_miss(self):
        tracker = self.Tracker()
        tracker.record_miss(tokens_written=200)
        assert tracker.cache_misses == 1
        assert tracker.cache_writes == 200

    def test_hit_rate(self):
        tracker = self.Tracker()
        tracker.record_hit(500)
        tracker.record_hit(300)
        tracker.record_miss(200)
        assert abs(tracker.hit_rate - 0.667) < 0.01

    def test_hit_rate_zero(self):
        tracker = self.Tracker()
        assert tracker.hit_rate == 0.0

    def test_events_log(self):
        tracker = self.Tracker()
        tracker.record_hit(500)
        tracker.record_miss(200)
        assert len(tracker.events) == 2
        assert tracker.events[0]["type"] == "cache_hit"
        assert tracker.events[1]["type"] == "cache_miss"

    def test_summary(self):
        tracker = self.Tracker()
        tracker.record_hit(1000)
        tracker.record_miss(200)
        summary = tracker.summary()
        assert "cache_hits" in summary
        assert "hit_rate" in summary
        assert "tokens_saved" in summary


# ============================================================================
# Task #9: Sandbox (Windows-adapted)
# ============================================================================

class TestSandboxWindows:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.sandbox import SandboxConfig, SandboxResult
        self.Config = SandboxConfig
        self.Result = SandboxResult

    def test_config_defaults(self):
        config = self.Config()
        assert config.restrict_cwd
        assert config.timeout_seconds == 30
        assert config.max_output_bytes == 16384

    def test_config_custom(self):
        config = self.Config(timeout_seconds=60, max_output_bytes=32000, clear_env_vars=True)
        assert config.timeout_seconds == 60
        assert config.clear_env_vars

    def test_sandbox_result_allowed(self):
        result = self.Result(allowed=True)
        assert result.allowed
        assert not result.blocked

    def test_sandbox_result_blocked(self):
        result = self.Result(allowed=False, reason="outside workspace")
        assert result.blocked
        assert "outside" in result.reason

    def test_sandbox_result_with_output(self):
        result = self.Result(allowed=True, output="hello", truncated=False)
        assert result.output == "hello"

    def test_truncate_output(self):
        config = self.Config(max_output_bytes=10)
        output = "x" * 100
        truncated = config.truncate_output(output)
        assert len(truncated) < len(output)
        assert "truncated" in truncated.lower()


# ============================================================================
# Task #10: Policy Engine
# ============================================================================

class TestPolicyEngine:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.policy_engine import PolicyEngine, PolicyRule, PolicyCondition, PolicyAction
        self.Engine = PolicyEngine
        self.Rule = PolicyRule
        self.Condition = PolicyCondition
        self.Action = PolicyAction

    def test_empty_engine_no_match(self):
        engine = self.Engine()
        actions = engine.evaluate({})
        assert actions == []

    def test_simple_rule_match(self):
        engine = self.Engine()
        engine.add_rule(self.Rule(
            name="retry_on_timeout",
            condition=self.Condition(key="retry_available", value=True),
            action=self.Action.RETRY,
        ))
        actions = engine.evaluate({"retry_available": True})
        assert len(actions) == 1
        assert actions[0].action == self.Action.RETRY

    def test_rule_no_match(self):
        engine = self.Engine()
        engine.add_rule(self.Rule(
            name="retry_on_timeout",
            condition=self.Condition(key="retry_available", value=True),
            action=self.Action.RETRY,
        ))
        actions = engine.evaluate({"retry_available": False})
        assert actions == []

    def test_multiple_rules_priority(self):
        engine = self.Engine()
        engine.add_rule(self.Rule(
            name="low_prio", condition=self.Condition(key="x", value=True),
            action=self.Action.LOG, priority=100,
        ))
        engine.add_rule(self.Rule(
            name="high_prio", condition=self.Condition(key="x", value=True),
            action=self.Action.ESCALATE, priority=10,
        ))
        actions = engine.evaluate({"x": True})
        assert actions[0].action == self.Action.ESCALATE  # lower number = higher priority

    def test_condition_with_threshold(self):
        engine = self.Engine()
        engine.add_rule(self.Rule(
            name="timeout",
            condition=self.Condition(key="elapsed_seconds", threshold=60),
            action=self.Action.ESCALATE,
        ))
        actions = engine.evaluate({"elapsed_seconds": 120})
        assert len(actions) == 1
        actions2 = engine.evaluate({"elapsed_seconds": 30})
        assert len(actions2) == 0

    def test_action_values(self):
        assert self.Action.RETRY.value == "retry"
        assert self.Action.ESCALATE.value == "escalate"
        assert self.Action.LOG.value == "log"
        assert self.Action.ABORT.value == "abort"

    def test_rule_to_dict(self):
        rule = self.Rule(
            name="test", condition=self.Condition(key="x", value=True),
            action=self.Action.LOG, priority=50,
        )
        d = rule.to_dict()
        assert d["name"] == "test"
        assert d["action"] == "log"
