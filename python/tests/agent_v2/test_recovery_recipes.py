"""TDD tests for Recovery Recipes — automatic fault recovery strategies.

Reference: claw-code rust/crates/runtime/src/recovery_recipes.rs

Adapted for academic writing scenarios:
  - ProviderFailure: LLM API timeout / key error → fallback provider
  - McpHandshakeFailure: MCP server won't start → restart
  - PartialPluginStartup: plugin stall → restart + retry
  - TrustPromptUnresolved: permission gate → auto-accept
  - PromptMisdelivery: prompt lost → redirect
  - StaleBranch: git branch stale → rebase
  - CompileRedCrossCrate: build failure → clean rebuild

Tests cover:
  1. FailureScenario enum + recipe_for
  2. RecoveryContext (attempt tracking, event log, ledger)
  3. attempt_recovery — success / partial / escalation
  4. Max attempts enforcement
  5. Ledger entry lifecycle (Queued→Running→Succeeded/Failed/Exhausted)
  6. StatusReport projection
"""
from __future__ import annotations

import pytest


# ============================================================================
# 1. FailureScenario enum
# ============================================================================

class TestFailureScenario:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.recovery import FailureScenario
        self.FS = FailureScenario

    def test_all_scenarios_defined(self):
        all_scenarios = self.FS.all()
        assert len(all_scenarios) == 7

    def test_all_have_distinct_names(self):
        names = [s.value for s in self.FS.all()]
        assert len(names) == len(set(names))

    def test_from_worker_failure_kind(self):
        from src.agent_v2.runtime.recovery import FailureScenario as FS
        assert FS.from_worker_failure("trust_gate") == FS.TRUST_PROMPT_UNRESOLVED
        assert FS.from_worker_failure("tool_permission_gate") == FS.TRUST_PROMPT_UNRESOLVED
        assert FS.from_worker_failure("prompt_delivery") == FS.PROMPT_MISDELIVERY
        assert FS.from_worker_failure("protocol") == FS.MCP_HANDSHAKE_FAILURE
        assert FS.from_worker_failure("provider") == FS.PROVIDER_FAILURE
        assert FS.from_worker_failure("startup_no_evidence") == FS.PROVIDER_FAILURE
        assert FS.from_worker_failure("unknown_x") == FS.PROVIDER_FAILURE


# ============================================================================
# 2. recipe_for
# ============================================================================

class TestRecipeFor:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.recovery import recipe_for, FailureScenario, RecoveryRecipe
        self.recipe_for = recipe_for
        self.FS = FailureScenario

    def test_each_scenario_has_recipe(self):
        for scenario in self.FS.all():
            recipe = self.recipe_for(scenario)
            assert recipe is not None
            assert recipe.scenario == scenario
            assert len(recipe.steps) >= 1
            assert recipe.max_attempts >= 1

    def test_provider_failure_recipe(self):
        recipe = self.recipe_for(self.FS.PROVIDER_FAILURE)
        assert any("restart" in s.lower() or "fallback" in s.lower() for s in recipe.steps)

    def test_mcp_handshake_recipe(self):
        recipe = self.recipe_for(self.FS.MCP_HANDSHAKE_FAILURE)
        assert any("mcp" in s.lower() or "restart" in s.lower() or "retry" in s.lower() for s in recipe.steps)

    def test_escalation_policy_defined(self):
        for scenario in self.FS.all():
            recipe = self.recipe_for(scenario)
            assert recipe.escalation_policy in ("alert_human", "abort", "log_and_continue")


# ============================================================================
# 3. RecoveryContext
# ============================================================================

class TestRecoveryContext:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.recovery import RecoveryContext, FailureScenario
        self.Ctx = RecoveryContext
        self.FS = FailureScenario

    def test_initial_state_empty(self):
        ctx = self.Ctx()
        assert ctx.attempt_count(self.FS.PROVIDER_FAILURE) == 0
        assert len(ctx.events()) == 0
        assert ctx.ledger_entries() == []

    def test_attempt_count_increments(self):
        ctx = self.Ctx()
        from src.agent_v2.runtime.recovery import attempt_recovery
        attempt_recovery(self.FS.TRUST_PROMPT_UNRESOLVED, ctx)
        assert ctx.attempt_count(self.FS.TRUST_PROMPT_UNRESOLVED) == 1

    def test_ledger_entry_created(self):
        ctx = self.Ctx()
        from src.agent_v2.runtime.recovery import attempt_recovery
        attempt_recovery(self.FS.PROVIDER_FAILURE, ctx)
        entry = ctx.ledger_entry(self.FS.PROVIDER_FAILURE)
        assert entry is not None
        assert entry.attempt_count == 1

    def test_events_populated(self):
        ctx = self.Ctx()
        from src.agent_v2.runtime.recovery import attempt_recovery
        attempt_recovery(self.FS.TRUST_PROMPT_UNRESOLVED, ctx)
        assert len(ctx.events()) >= 2

    def test_status_report_not_attempted(self):
        ctx = self.Ctx()
        report = ctx.status_report(self.FS.PROVIDER_FAILURE)
        assert not report.attempted
        assert report.attempt_count == 0

    def test_status_report_after_attempt(self):
        ctx = self.Ctx()
        from src.agent_v2.runtime.recovery import attempt_recovery
        attempt_recovery(self.FS.PROVIDER_FAILURE, ctx)
        report = ctx.status_report(self.FS.PROVIDER_FAILURE)
        assert report.attempted

    def test_fail_at_step_configurable(self):
        ctx = self.Ctx().with_fail_at_step(0)
        assert ctx._fail_at_step == 0

    def test_ledger_entries_returns_all(self):
        ctx = self.Ctx()
        from src.agent_v2.runtime.recovery import attempt_recovery
        attempt_recovery(self.FS.PROVIDER_FAILURE, ctx)
        attempt_recovery(self.FS.MCP_HANDSHAKE_FAILURE, ctx)
        entries = ctx.ledger_entries()
        assert len(entries) == 2


# ============================================================================
# 4. attempt_recovery — outcomes
# ============================================================================

class TestAttemptRecovery:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.recovery import (
            RecoveryContext, FailureScenario, attempt_recovery,
            RecoveryResult,
        )
        self.Ctx = RecoveryContext
        self.FS = FailureScenario
        self.attempt = attempt_recovery
        self.Result = RecoveryResult

    def test_successful_recovery(self):
        ctx = self.Ctx()
        result = self.attempt(self.FS.TRUST_PROMPT_UNRESOLVED, ctx)
        assert result.is_recovered
        assert result.steps_taken >= 1

    def test_recovery_emits_succeeded_event(self):
        ctx = self.Ctx()
        self.attempt(self.FS.TRUST_PROMPT_UNRESOLVED, ctx)
        events = ctx.events()
        event_types = [e["type"] for e in events]
        assert "recovery_succeeded" in event_types

    def test_escalation_after_max_attempts(self):
        ctx = self.Ctx()
        # First attempt succeeds
        r1 = self.attempt(self.FS.PROMPT_MISDELIVERY, ctx)
        assert r1.is_recovered

        # Second attempt escalates
        r2 = self.attempt(self.FS.PROMPT_MISDELIVERY, ctx)
        assert r2.is_escalation_required
        assert "max recovery attempts" in r2.reason.lower() or "exceeded" in r2.reason.lower()

    def test_escalation_emits_escalated_event(self):
        ctx = self.Ctx()
        self.attempt(self.FS.PROMPT_MISDELIVERY, ctx)
        self.attempt(self.FS.PROMPT_MISDELIVERY, ctx)
        events = ctx.events()
        event_types = [e["type"] for e in events]
        assert "escalated" in event_types

    def test_partial_recovery_when_step_fails(self):
        """If recovery fails at a mid-step, partial recovery is returned."""
        ctx = self.Ctx().with_fail_at_step(1)
        # PartialPluginStartup has multiple steps
        result = self.attempt(self.FS.PARTIAL_PLUGIN_STARTUP, ctx)
        assert result.is_partial_recovery or result.is_escalation_required

    def test_first_step_failure_escalates(self):
        """If recovery fails at the first step, escalation is required."""
        ctx = self.Ctx().with_fail_at_step(0)
        result = self.attempt(self.FS.PROVIDER_FAILURE, ctx)
        assert result.is_escalation_required

    def test_ledger_lifecycle_queued_to_running_to_succeeded(self):
        ctx = self.Ctx()
        self.attempt(self.FS.TRUST_PROMPT_UNRESOLVED, ctx)
        entry = ctx.ledger_entry(self.FS.TRUST_PROMPT_UNRESOLVED)
        assert entry.state == "succeeded"

    def test_ledger_lifecycle_to_exhausted(self):
        ctx = self.Ctx()
        self.attempt(self.FS.PROMPT_MISDELIVERY, ctx)
        self.attempt(self.FS.PROMPT_MISDELIVERY, ctx)
        entry = ctx.ledger_entry(self.FS.PROMPT_MISDELIVERY)
        assert entry.state == "exhausted"

    def test_command_results_populated(self):
        ctx = self.Ctx()
        self.attempt(self.FS.TRUST_PROMPT_UNRESOLVED, ctx)
        entry = ctx.ledger_entry(self.FS.TRUST_PROMPT_UNRESOLVED)
        assert len(entry.command_results) >= 1
        assert entry.command_results[0]["status"] == "succeeded"


# ============================================================================
# 5. RecoveryResult types
# ============================================================================

class TestRecoveryResult:

    def test_recovered(self):
        from src.agent_v2.runtime.recovery import RecoveryResult
        r = RecoveryResult.recovered(steps_taken=3)
        assert r.is_recovered
        assert not r.is_partial_recovery
        assert not r.is_escalation_required
        assert r.steps_taken == 3

    def test_partial_recovery(self):
        from src.agent_v2.runtime.recovery import RecoveryResult
        r = RecoveryResult.partial_recovery(
            recovered=["step1"], remaining=["step2"]
        )
        assert r.is_partial_recovery
        assert not r.is_recovered
        assert len(r.recovered) == 1
        assert len(r.remaining) == 1

    def test_escalation_required(self):
        from src.agent_v2.runtime.recovery import RecoveryResult
        r = RecoveryResult.escalation_required(reason="too many attempts")
        assert r.is_escalation_required
        assert "too many" in r.reason

    def test_to_dict(self):
        from src.agent_v2.runtime.recovery import RecoveryResult
        r = RecoveryResult.recovered(steps_taken=2)
        d = r.to_dict()
        assert d["type"] == "recovered"
        assert d["steps_taken"] == 2
