"""Policy Engine — condition-driven rule evaluation for agent behavior.

Port of claw-code rust/crates/runtime/src/policy_engine.rs.

Declarative rules: Condition(key=value|threshold) → Action(RETRY|ESCALATE|LOG|ABORT).
Evaluated against a context dict, ordered by priority (lower = higher priority).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PolicyAction(Enum):
    RETRY = "retry"
    ESCALATE = "escalate"
    LOG = "log"
    ABORT = "abort"


@dataclass
class PolicyCondition:
    key: str
    value: Any = None
    threshold: float | None = None

    def matches(self, context: dict[str, Any]) -> bool:
        if self.key not in context:
            return False
        ctx_val = context[self.key]
        if self.threshold is not None:
            return isinstance(ctx_val, (int, float)) and ctx_val >= self.threshold
        return ctx_val == self.value


@dataclass
class PolicyRule:
    name: str
    condition: PolicyCondition
    action: PolicyAction
    priority: int = 50

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "action": self.action.value, "priority": self.priority}


@dataclass
class MatchedAction:
    rule_name: str
    action: PolicyAction
    priority: int


class PolicyEngine:
    """Evaluate policy rules against a context dict."""

    def __init__(self):
        self._rules: list[PolicyRule] = []

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def evaluate(self, context: dict[str, Any]) -> list[MatchedAction]:
        results: list[MatchedAction] = []
        for rule in self._rules:
            if rule.condition.matches(context):
                results.append(MatchedAction(
                    rule_name=rule.name, action=rule.action, priority=rule.priority,
                ))
        return results
