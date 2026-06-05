"""Recovery Recipes — automatic fault recovery for known failure scenarios.

Port of claw-code rust/crates/runtime/src/recovery_recipes.rs.

7 failure scenarios with known recovery recipes:
  - TrustPromptUnresolved → AcceptTrustPrompt
  - PromptMisdelivery → RedirectPromptToAgent
  - StaleBranch → RebaseBranch + CleanBuild
  - CompileRedCrossCrate → CleanBuild
  - McpHandshakeFailure → RetryMcpHandshake
  - PartialPluginStartup → RestartPlugin + RetryMcpHandshake
  - ProviderFailure → RestartWorker / FallbackProvider

Enforces one automatic recovery attempt before escalation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class FailureScenario(Enum):
    TRUST_PROMPT_UNRESOLVED = "trust_prompt_unresolved"
    PROMPT_MISDELIVERY = "prompt_misdelivery"
    STALE_BRANCH = "stale_branch"
    COMPILE_RED_CRATE = "compile_red_cross_crate"
    MCP_HANDSHAKE_FAILURE = "mcp_handshake_failure"
    PARTIAL_PLUGIN_STARTUP = "partial_plugin_startup"
    PROVIDER_FAILURE = "provider_failure"

    @staticmethod
    def all() -> list[FailureScenario]:
        return list(FailureScenario)

    @staticmethod
    def from_worker_failure(kind: str) -> FailureScenario:
        mapping = {
            "trust_gate": FailureScenario.TRUST_PROMPT_UNRESOLVED,
            "tool_permission_gate": FailureScenario.TRUST_PROMPT_UNRESOLVED,
            "prompt_delivery": FailureScenario.PROMPT_MISDELIVERY,
            "protocol": FailureScenario.MCP_HANDSHAKE_FAILURE,
            "provider": FailureScenario.PROVIDER_FAILURE,
            "startup_no_evidence": FailureScenario.PROVIDER_FAILURE,
        }
        return mapping.get(kind, FailureScenario.PROVIDER_FAILURE)


class RecoveryAttemptState(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


@dataclass
class RecoveryResult:
    _type: str = ""
    steps_taken: int = 0
    recovered: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    reason: str = ""

    @staticmethod
    def recovered(steps_taken: int) -> RecoveryResult:
        return RecoveryResult(_type="recovered", steps_taken=steps_taken)

    @staticmethod
    def partial_recovery(recovered: list[str], remaining: list[str]) -> RecoveryResult:
        return RecoveryResult(_type="partial_recovery", recovered=recovered, remaining=remaining)

    @staticmethod
    def escalation_required(reason: str) -> RecoveryResult:
        return RecoveryResult(_type="escalation_required", reason=reason)

    @property
    def is_recovered(self) -> bool:
        return self._type == "recovered"

    @property
    def is_partial_recovery(self) -> bool:
        return self._type == "partial_recovery"

    @property
    def is_escalation_required(self) -> bool:
        return self._type == "escalation_required"

    def to_dict(self) -> dict:
        return {"type": self._type, "steps_taken": self.steps_taken,
                "recovered": self.recovered, "remaining": self.remaining,
                "reason": self.reason}


@dataclass
class RecoveryRecipe:
    scenario: FailureScenario
    steps: list[str]
    max_attempts: int
    escalation_policy: str


@dataclass
class RecoveryCommandResult:
    command: str
    status: str
    result: str


@dataclass
class RecoveryLedgerEntry:
    recipe_id: str
    trigger: FailureScenario
    attempt_count: int = 0
    retry_limit: int = 0
    attempts_remaining: int = 0
    state: str = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    command_results: list[dict] = field(default_factory=list)
    result: RecoveryResult | None = None
    last_failure_summary: str | None = None
    escalation_reason: str | None = None


@dataclass
class RecoveryStatusReport:
    scenario: FailureScenario
    attempted: bool
    state: str | None = None
    attempt_count: int = 0
    retry_limit: int | None = None
    attempts_remaining: int | None = None
    escalation_reason: str | None = None


# ---------------------------------------------------------------------------
# Recipe lookup
# ---------------------------------------------------------------------------

def recipe_for(scenario: FailureScenario) -> RecoveryRecipe:
    recipes = {
        FailureScenario.TRUST_PROMPT_UNRESOLVED: RecoveryRecipe(
            scenario=scenario, steps=["AcceptTrustPrompt"],
            max_attempts=1, escalation_policy="alert_human"),
        FailureScenario.PROMPT_MISDELIVERY: RecoveryRecipe(
            scenario=scenario, steps=["RedirectPromptToAgent"],
            max_attempts=1, escalation_policy="alert_human"),
        FailureScenario.STALE_BRANCH: RecoveryRecipe(
            scenario=scenario, steps=["RebaseBranch", "CleanBuild"],
            max_attempts=1, escalation_policy="alert_human"),
        FailureScenario.COMPILE_RED_CRATE: RecoveryRecipe(
            scenario=scenario, steps=["CleanBuild"],
            max_attempts=1, escalation_policy="alert_human"),
        FailureScenario.MCP_HANDSHAKE_FAILURE: RecoveryRecipe(
            scenario=scenario, steps=["RetryMcpHandshake(timeout=5000)"],
            max_attempts=1, escalation_policy="abort"),
        FailureScenario.PARTIAL_PLUGIN_STARTUP: RecoveryRecipe(
            scenario=scenario, steps=["RestartPlugin(stalled)", "RetryMcpHandshake(timeout=3000)"],
            max_attempts=1, escalation_policy="log_and_continue"),
        FailureScenario.PROVIDER_FAILURE: RecoveryRecipe(
            scenario=scenario, steps=["RestartWorker"],
            max_attempts=1, escalation_policy="alert_human"),
    }
    return recipes[scenario]


# ---------------------------------------------------------------------------
# RecoveryContext
# ---------------------------------------------------------------------------

class RecoveryContext:
    """Tracks per-scenario attempt counts, events, and ledger."""

    def __init__(self) -> None:
        self._attempts: dict[FailureScenario, int] = {}
        self._events: list[dict] = []
        self._ledger: dict[FailureScenario, RecoveryLedgerEntry] = {}
        self._clock_tick: int = 0
        self._fail_at_step: int | None = None

    def with_fail_at_step(self, index: int) -> RecoveryContext:
        self._fail_at_step = index
        return self

    def attempt_count(self, scenario: FailureScenario) -> int:
        return self._attempts.get(scenario, 0)

    def events(self) -> list[dict]:
        return self._events

    def ledger_entry(self, scenario: FailureScenario) -> RecoveryLedgerEntry | None:
        return self._ledger.get(scenario)

    def ledger_entries(self) -> list[RecoveryLedgerEntry]:
        entries = list(self._ledger.values())
        entries.sort(key=lambda e: e.recipe_id)
        return entries

    def status_report(self, scenario: FailureScenario) -> RecoveryStatusReport:
        entry = self._ledger.get(scenario)
        if entry is None:
            return RecoveryStatusReport(scenario=scenario, attempted=False)
        return RecoveryStatusReport(
            scenario=scenario, attempted=entry.attempt_count > 0,
            state=entry.state, attempt_count=entry.attempt_count,
            retry_limit=entry.retry_limit, attempts_remaining=entry.attempts_remaining,
            escalation_reason=entry.escalation_reason,
        )

    def _next_timestamp(self) -> str:
        self._clock_tick += 1
        return f"recovery-ledger-tick-{self._clock_tick}"


# ---------------------------------------------------------------------------
# attempt_recovery
# ---------------------------------------------------------------------------

def attempt_recovery(scenario: FailureScenario, ctx: RecoveryContext) -> RecoveryResult:
    """Attempt automatic recovery for the given failure scenario."""
    recipe = recipe_for(scenario)
    recipe_id = scenario.value

    # Initialize ledger entry if needed
    ctx._ledger.setdefault(scenario, RecoveryLedgerEntry(
        recipe_id=recipe_id, trigger=scenario, retry_limit=recipe.max_attempts,
        attempts_remaining=recipe.max_attempts,
    ))

    current_attempts = ctx._attempts.get(scenario, 0)

    # Enforce max attempts
    if current_attempts >= recipe.max_attempts:
        reason = f"max recovery attempts ({recipe.max_attempts}) exceeded for {scenario.value}"
        result = RecoveryResult.escalation_required(reason)
        finished_at = ctx._next_timestamp()
        entry = ctx._ledger[scenario]
        entry.attempt_count = current_attempts
        entry.attempts_remaining = 0
        entry.state = "exhausted"
        entry.finished_at = finished_at
        entry.result = result
        entry.last_failure_summary = reason
        entry.escalation_reason = reason
        ctx._events.append({"type": "recovery_attempted", "scenario": scenario.value,
                             "result": result.to_dict()})
        ctx._events.append({"type": "escalated"})
        return result

    # Increment attempts
    ctx._attempts[scenario] = current_attempts + 1
    updated_attempts = ctx._attempts[scenario]
    started_at = ctx._next_timestamp()
    entry = ctx._ledger[scenario]
    entry.attempt_count = updated_attempts
    entry.attempts_remaining = max(0, recipe.max_attempts - updated_attempts)
    entry.state = "running"
    entry.started_at = started_at
    entry.finished_at = None
    entry.command_results = []
    entry.result = None
    entry.last_failure_summary = None
    entry.escalation_reason = None

    # Execute steps with optional fail_at_step
    executed: list[str] = []
    command_results: list[dict] = []
    failed = False

    for i, step in enumerate(recipe.steps):
        if ctx._fail_at_step == i:
            command_results.append({"command": step, "status": "failed",
                                     "result": f"step {i} failed for {scenario.value}"})
            failed = True
            break
        executed.append(step)
        command_results.append({"command": step, "status": "succeeded",
                                 "result": f"step {i} succeeded for {scenario.value}"})

    if failed:
        remaining = recipe.steps[len(executed):]
        if not executed:
            result = RecoveryResult.escalation_required(
                f"recovery failed at first step for {scenario.value}")
        else:
            result = RecoveryResult.partial_recovery(recovered=executed, remaining=remaining)
    else:
        result = RecoveryResult.recovered(steps_taken=len(recipe.steps))

    # Update ledger
    finished_at = ctx._next_timestamp()
    entry.finished_at = finished_at
    entry.command_results = command_results
    entry.result = result
    if result.is_recovered:
        entry.state = "succeeded"
    elif result.is_partial_recovery:
        entry.state = "failed"
        entry.last_failure_summary = f"{len(result.remaining)} step(s) remaining after partial recovery"
    else:
        entry.state = "exhausted"
        entry.last_failure_summary = result.reason
        entry.escalation_reason = result.reason

    # Emit events
    ctx._events.append({"type": "recovery_attempted", "scenario": scenario.value,
                         "result": result.to_dict()})
    if result.is_recovered:
        ctx._events.append({"type": "recovery_succeeded"})
    elif result.is_partial_recovery:
        ctx._events.append({"type": "recovery_failed"})
    else:
        ctx._events.append({"type": "escalated"})

    return result
