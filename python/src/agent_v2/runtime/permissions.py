"""PermissionPolicy — 5 级权限 + allow/deny/ask 规则引擎。

参考 claw-code runtime/permissions.rs:
  - PermissionMode: ReadOnly < WorkspaceWrite < DangerFullAccess + Prompt + Allow
  - PermissionPolicy: authorize() with rule-based evaluation
  - Rule matching: exact, prefix (tool_name(pattern))
  - Hook overrides: Allow/Deny/Ask
  - denied_tools: unconditional denial
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol


class PermissionMode(Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"
    PROMPT = "prompt"
    ALLOW = "allow"

    def __lt__(self, other: PermissionMode) -> bool:
        order = {
            PermissionMode.READ_ONLY: 0,
            PermissionMode.WORKSPACE_WRITE: 1,
            PermissionMode.DANGER_FULL_ACCESS: 2,
        }
        return order.get(self, 99) < order.get(other, 99)

    def __le__(self, other: PermissionMode) -> bool:
        return self == other or self < other

    def __gt__(self, other: PermissionMode) -> bool:
        return not self <= other

    def __ge__(self, other: PermissionMode) -> bool:
        return not self < other


class PermissionOutcome(Enum):
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


@dataclass
class DenyResult:
    reason: str

    @property
    def outcome(self) -> PermissionOutcome:
        return PermissionOutcome.DENY

    @property
    def is_denied(self) -> bool:
        return True

    @property
    def needs_approval(self) -> bool:
        return False

    @property
    def is_allowed(self) -> bool:
        return False


@dataclass
class AllowResult:
    reason: str = ""

    @property
    def outcome(self) -> PermissionOutcome:
        return PermissionOutcome.ALLOW

    @property
    def is_denied(self) -> bool:
        return False

    @property
    def needs_approval(self) -> bool:
        return False

    @property
    def is_allowed(self) -> bool:
        return True


@dataclass
class PromptResult:
    reason: str

    @property
    def outcome(self) -> PermissionOutcome:
        return PermissionOutcome.PROMPT

    @property
    def is_denied(self) -> bool:
        return False

    @property
    def needs_approval(self) -> bool:
        return True

    @property
    def is_allowed(self) -> bool:
        return False


PermissionResult = AllowResult | DenyResult | PromptResult


class PermissionOverride(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionContext:
    override: PermissionOverride | None = None
    override_reason: str = ""


class PermissionPrompter(Protocol):
    def decide(self, request: PermissionRequest) -> PermissionDecision:
        ...


@dataclass
class PermissionRequest:
    tool_name: str
    input: str
    current_mode: PermissionMode
    required_mode: PermissionMode
    reason: str | None = None


@dataclass
class PermissionDecision:
    allow: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Rule parsing
# ---------------------------------------------------------------------------

class _RuleMatcher(Enum):
    ANY = auto()
    EXACT = auto()
    PREFIX = auto()


@dataclass
class _PermissionRule:
    raw: str
    tool_name: str
    matcher: _RuleMatcher = _RuleMatcher.ANY
    pattern: str = ""

    def matches(self, tool_name: str, input_str: str) -> bool:
        if self.tool_name != tool_name:
            return False
        if self.matcher == _RuleMatcher.ANY:
            return True
        subject = _extract_subject(input_str)
        if self.matcher == _RuleMatcher.EXACT:
            return subject == self.pattern
        if self.matcher == _RuleMatcher.PREFIX:
            return subject is not None and subject.startswith(self.pattern)
        return False


def _parse_rule(raw: str) -> _PermissionRule:
    trimmed = raw.strip()
    # Check for tool(pattern) syntax
    m = re.match(r'^(\w+)\((.*)\)$', trimmed)
    if m:
        tool_name = m.group(1)
        content = m.group(2).strip()
        if content in ("", "*"):
            return _PermissionRule(raw=trimmed, tool_name=tool_name, matcher=_RuleMatcher.ANY)
        if content.endswith(":*"):
            return _PermissionRule(raw=trimmed, tool_name=tool_name, matcher=_RuleMatcher.PREFIX, pattern=content[:-2])
        return _PermissionRule(raw=trimmed, tool_name=tool_name, matcher=_RuleMatcher.EXACT, pattern=content)
    return _PermissionRule(raw=trimmed, tool_name=trimmed, matcher=_RuleMatcher.ANY)


def _extract_subject(input_str: str) -> str | None:
    try:
        obj = json.loads(input_str)
        if isinstance(obj, dict):
            for key in ("command", "path", "file_path", "filePath", "pattern", "code", "message"):
                if key in obj and isinstance(obj[key], str):
                    return obj[key]
    except (json.JSONDecodeError, TypeError):
        pass
    return input_str.strip() if input_str.strip() else None


# ---------------------------------------------------------------------------
# PermissionPolicy
# ---------------------------------------------------------------------------

class PermissionPolicy:
    """5 级权限 + allow/deny/ask 规则引擎。

    Evaluation order (参考 claw-code permissions.rs authorize_with_context):
      1. denied_tools 黑名单 → unconditional Deny
      2. deny_rules → Deny
      3. Hook override Deny → short-circuit Deny
      4. Hook override Ask → Prompt (unless ask_rule exists, which always prompts)
      5. ask_rules → Prompt
      6. Hook override Allow → check ask_rules first, then allow
      7. allow_rules → Allow
      8. Mode comparison → Allow/Deny/Prompt
    """

    def __init__(
        self,
        active_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        tool_requirements: dict[str, PermissionMode] | None = None,
        allow_rules: list[str] | None = None,
        deny_rules: list[str] | None = None,
        ask_rules: list[str] | None = None,
        denied_tools: list[str] | None = None,
    ):
        self.active_mode = active_mode
        self._tool_requirements = tool_requirements or {}
        self._allow_rules = [_parse_rule(r) for r in (allow_rules or [])]
        self._deny_rules = [_parse_rule(r) for r in (deny_rules or [])]
        self._ask_rules = [_parse_rule(r) for r in (ask_rules or [])]
        self._denied_tools = set(denied_tools or [])

    def required_mode_for(self, tool_name: str) -> PermissionMode:
        return self._tool_requirements.get(tool_name, PermissionMode.DANGER_FULL_ACCESS)

    def authorize(
        self,
        tool_name: str,
        input_str: str,
        context: PermissionContext | None = None,
        prompter: PermissionPrompter | None = None,
    ) -> PermissionResult:
        ctx = context or PermissionContext()

        # 1. denied_tools 黑名单
        if tool_name in self._denied_tools:
            return DenyResult(reason=f"tool '{tool_name}' denied by denied_tools configuration")

        # 2. deny_rules
        for rule in self._deny_rules:
            if rule.matches(tool_name, input_str):
                return DenyResult(reason=f"denied by rule '{rule.raw}'")

        # 3. Hook override Deny
        if ctx.override == PermissionOverride.DENY:
            return DenyResult(reason=ctx.override_reason or f"tool '{tool_name}' denied by hook")

        # 4-5. ask_rules
        ask_match = next((r for r in self._ask_rules if r.matches(tool_name, input_str)), None)

        # 4. Hook override Ask
        if ctx.override == PermissionOverride.ASK:
            reason = ctx.override_reason or f"tool '{tool_name}' requires approval due to hook"
            return self._prompt_or_deny(tool_name, input_str, reason, prompter)

        # 5. ask_rules match
        if ask_match:
            return self._prompt_or_deny(tool_name, input_str, f"requires approval due to ask rule '{ask_match.raw}'", prompter)

        # 6. Hook override Allow (still respects ask_rules)
        if ctx.override == PermissionOverride.ALLOW:
            if self.active_mode == PermissionMode.ALLOW:
                return AllowResult()
            if self.active_mode >= self.required_mode_for(tool_name):
                return AllowResult()
            return self._prompt_or_deny(tool_name, input_str, f"mode escalation needed", prompter)

        # 7. allow_rules
        allow_match = next((r for r in self._allow_rules if r.matches(tool_name, input_str)), None)
        if allow_match:
            return AllowResult(reason=f"allowed by rule '{allow_match.raw}'")

        # 8. Mode comparison
        if self.active_mode == PermissionMode.ALLOW:
            return AllowResult()
        if self.active_mode == PermissionMode.PROMPT:
            return self._prompt_or_deny(tool_name, input_str, f"prompt mode: approval required for '{tool_name}'", prompter)
        if self.active_mode >= self.required_mode_for(tool_name):
            return AllowResult()
        if self.active_mode == PermissionMode.WORKSPACE_WRITE and self.required_mode_for(tool_name) == PermissionMode.DANGER_FULL_ACCESS:
            return self._prompt_or_deny(tool_name, input_str, f"'{tool_name}' requires escalation to danger-full-access", prompter)

        return DenyResult(reason=f"'{tool_name}' requires {self.required_mode_for(tool_name).value} permission; current mode is {self.active_mode.value}")

    def _prompt_or_deny(self, tool_name: str, input_str: str, reason: str, prompter: PermissionPrompter | None) -> PermissionResult:
        if prompter is None:
            return DenyResult(reason=reason)
        request = PermissionRequest(
            tool_name=tool_name,
            input=input_str,
            current_mode=self.active_mode,
            required_mode=self.required_mode_for(tool_name),
            reason=reason,
        )
        try:
            decision = prompter.decide(request)
        except Exception:
            return DenyResult(reason=f"prompter error for '{tool_name}': {reason}")
        if decision.allow:
            return AllowResult(reason=f"approved: {decision.reason}")
        return DenyResult(reason=decision.reason or reason)


# ---------------------------------------------------------------------------
# Helper: build policy from tool registry permission specs
# ---------------------------------------------------------------------------

def policy_from_registry(
    active_mode: PermissionMode,
    tool_permissions: list[tuple[str, str]],
    **kwargs: Any,
) -> PermissionPolicy:
    tool_reqs: dict[str, PermissionMode] = {}
    mode_map = {
        "read-only": PermissionMode.READ_ONLY,
        "workspace-write": PermissionMode.WORKSPACE_WRITE,
        "danger-full-access": PermissionMode.DANGER_FULL_ACCESS,
    }
    for name, perm in tool_permissions:
        tool_reqs[name] = mode_map.get(perm, PermissionMode.DANGER_FULL_ACCESS)
    return PermissionPolicy(active_mode=active_mode, tool_requirements=tool_reqs, **kwargs)
