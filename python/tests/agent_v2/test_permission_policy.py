"""PermissionPolicy 测试 — PP-001 ~ PP-052。"""
from __future__ import annotations

import pytest

from src.agent_v2.runtime.permissions import (
    AllowResult,
    DenyResult,
    PermissionContext,
    PermissionDecision,
    PermissionMode,
    PermissionPolicy,
    PermissionPrompter,
    PermissionRequest,
    PermissionOverride,
    PromptResult,
    policy_from_registry,
)


# Helper prompter
class RecordingPrompter:
    def __init__(self, allow: bool = True, reason: str = "ok"):
        self.seen: list[PermissionRequest] = []
        self.allow = allow
        self.reason = reason

    def decide(self, request: PermissionRequest) -> PermissionDecision:
        self.seen.append(request)
        return PermissionDecision(allow=self.allow, reason=self.reason)


def _default_tool_reqs() -> dict[str, PermissionMode]:
    return {
        "read_file": PermissionMode.READ_ONLY,
        "write_file": PermissionMode.WORKSPACE_WRITE,
        "str_replace": PermissionMode.WORKSPACE_WRITE,
        "bash": PermissionMode.DANGER_FULL_ACCESS,
        "run_command": PermissionMode.DANGER_FULL_ACCESS,
    }


# ============================================================================
# 4.1 权限级别
# ============================================================================

class TestPermissionLevels:

    def test_pp001_readonly_allows_read(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, _default_tool_reqs())
        result = policy.authorize("read_file", "{}")
        assert isinstance(result, AllowResult)

    def test_pp002_readonly_denies_write(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, _default_tool_reqs())
        result = policy.authorize("write_file", '{"file_path":"a.txt","content":"x"}')
        assert isinstance(result, DenyResult)

    def test_pp003_readonly_denies_bash(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, _default_tool_reqs())
        result = policy.authorize("bash", '{"command":"ls"}')
        assert isinstance(result, DenyResult)

    def test_pp004_wswrite_allows_write(self):
        policy = PermissionPolicy(PermissionMode.WORKSPACE_WRITE, _default_tool_reqs())
        result = policy.authorize("write_file", '{"file_path":"a.txt","content":"x"}')
        assert isinstance(result, AllowResult)

    def test_pp005_wswrite_allows_replace(self):
        policy = PermissionPolicy(PermissionMode.WORKSPACE_WRITE, _default_tool_reqs())
        result = policy.authorize("str_replace", '{"file_path":"a.txt","old_string":"x","new_string":"y"}')
        assert isinstance(result, AllowResult)

    def test_pp006_wswrite_denies_bash(self):
        policy = PermissionPolicy(PermissionMode.WORKSPACE_WRITE, _default_tool_reqs())
        result = policy.authorize("bash", '{"command":"ls"}')
        assert isinstance(result, DenyResult)

    def test_pp007_danger_allows_all(self):
        policy = PermissionPolicy(PermissionMode.DANGER_FULL_ACCESS, _default_tool_reqs())
        assert isinstance(policy.authorize("read_file", "{}"), AllowResult)
        assert isinstance(policy.authorize("write_file", "{}"), AllowResult)
        assert isinstance(policy.authorize("bash", "{}"), AllowResult)

    def test_pp008_prompt_mode(self):
        policy = PermissionPolicy(PermissionMode.PROMPT, _default_tool_reqs())
        prompter = RecordingPrompter(allow=True)
        result = policy.authorize("read_file", "{}", prompter=prompter)
        assert isinstance(result, AllowResult)
        assert len(prompter.seen) == 1

    def test_pp009_allow_mode(self):
        policy = PermissionPolicy(PermissionMode.ALLOW, _default_tool_reqs())
        assert isinstance(policy.authorize("bash", "{}"), AllowResult)


# ============================================================================
# 4.2 规则引擎
# ============================================================================

class TestRuleEngine:

    def test_pp010_deny_rule(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            deny_rules=["bash(rm -rf:*)"],
        )
        result = policy.authorize("bash", '{"command":"rm -rf /tmp/x"}')
        assert isinstance(result, DenyResult)
        assert "denied by rule" in result.reason

    def test_pp011_allow_rule(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            allow_rules=["bash(git:*)"],
        )
        result = policy.authorize("bash", '{"command":"git status"}')
        assert isinstance(result, AllowResult)

    def test_pp012_ask_rule(self):
        policy = PermissionPolicy(
            PermissionMode.ALLOW, _default_tool_reqs(),
            ask_rules=["bash(git push:*)"],
        )
        prompter = RecordingPrompter(allow=True)
        result = policy.authorize("bash", '{"command":"git push origin main"}', prompter=prompter)
        assert isinstance(result, AllowResult)
        assert len(prompter.seen) == 1

    def test_pp013_denied_tools(self):
        policy = PermissionPolicy(
            PermissionMode.DANGER_FULL_ACCESS, _default_tool_reqs(),
            denied_tools=["bash"],
        )
        result = policy.authorize("bash", '{"command":"echo hi"}')
        assert isinstance(result, DenyResult)
        assert "denied_tools" in result.reason

    def test_pp014_deny_over_allow(self):
        policy = PermissionPolicy(
            PermissionMode.ALLOW, _default_tool_reqs(),
            deny_rules=["bash(rm:*)"],
            allow_rules=["bash(rm:*)"],
        )
        result = policy.authorize("bash", '{"command":"rm file"}')
        assert isinstance(result, DenyResult)

    def test_pp015_ask_over_mode(self):
        policy = PermissionPolicy(
            PermissionMode.ALLOW, _default_tool_reqs(),
            ask_rules=["read_file(*)"],
        )
        prompter = RecordingPrompter(allow=True)
        result = policy.authorize("read_file", '{"file_path":"a.txt"}', prompter=prompter)
        assert len(prompter.seen) == 1

    def test_pp016_priority_order(self):
        policy = PermissionPolicy(
            PermissionMode.DANGER_FULL_ACCESS, _default_tool_reqs(),
            denied_tools=["bash"],
            deny_rules=["bash(git:*)"],
            allow_rules=["bash(echo:*)"],
        )
        # denied_tools wins
        result = policy.authorize("bash", '{"command":"echo hi"}')
        assert isinstance(result, DenyResult)
        assert "denied_tools" in result.reason


# ============================================================================
# 4.3 规则匹配
# ============================================================================

class TestRuleMatching:

    def test_pp020_exact_match(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            deny_rules=[f'write_file(/etc/hosts)'],
        )
        result = policy.authorize("write_file", '{"file_path":"/etc/hosts","content":"x"}')
        assert isinstance(result, DenyResult)
        # Different path — no match
        result2 = policy.authorize("write_file", '{"file_path":"/tmp/test","content":"x"}')
        assert not isinstance(result2, DenyResult) or "denied by rule" not in result2.reason

    def test_pp021_prefix_match(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            allow_rules=["bash(git:*)"],
        )
        result = policy.authorize("bash", '{"command":"git status"}')
        assert isinstance(result, AllowResult)
        result2 = policy.authorize("bash", '{"command":"git log --oneline"}')
        assert isinstance(result2, AllowResult)

    def test_pp022_wildcard_match(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            allow_rules=["read_file(*)"],
        )
        result = policy.authorize("read_file", '{"file_path":"anything.txt"}')
        assert isinstance(result, AllowResult)

    def test_pp023_tool_name_no_match(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            allow_rules=["bash(git:*)"],
        )
        result = policy.authorize("read_file", '{"command":"git status"}')
        # read_file is read-only, should be allowed by mode
        assert isinstance(result, AllowResult)

    def test_pp024_empty_json_input(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            deny_rules=["bash(*)"],
        )
        result = policy.authorize("bash", "{}")
        assert isinstance(result, DenyResult)

    def test_pp025_special_chars_in_path(self):
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            allow_rules=["read_file(*)"],
        )
        result = policy.authorize("read_file", '{"file_path":"/path/with spaces/中文 (1).txt"}')
        assert isinstance(result, AllowResult)


# ============================================================================
# 4.4 Hook 覆盖
# ============================================================================

class TestHookOverrides:

    def test_pp030_hook_allow_with_ask_rule(self):
        policy = PermissionPolicy(
            PermissionMode.ALLOW, _default_tool_reqs(),
            ask_rules=["bash(git:*)"],
        )
        prompter = RecordingPrompter(allow=True)
        ctx = PermissionContext(override=PermissionOverride.ALLOW)
        result = policy.authorize("bash", '{"command":"git push"}', context=ctx, prompter=prompter)
        assert len(prompter.seen) == 1

    def test_pp031_hook_deny_short_circuit(self):
        policy = PermissionPolicy(
            PermissionMode.DANGER_FULL_ACCESS, _default_tool_reqs(),
        )
        ctx = PermissionContext(override=PermissionOverride.DENY, override_reason="blocked by hook")
        result = policy.authorize("bash", '{"command":"echo hi"}', context=ctx)
        assert isinstance(result, DenyResult)
        assert "blocked by hook" in result.reason

    def test_pp032_hook_ask_forces_prompt(self):
        policy = PermissionPolicy(
            PermissionMode.DANGER_FULL_ACCESS, _default_tool_reqs(),
        )
        prompter = RecordingPrompter(allow=True)
        ctx = PermissionContext(override=PermissionOverride.ASK, override_reason="hook wants confirmation")
        result = policy.authorize("bash", '{"command":"echo hi"}', context=ctx, prompter=prompter)
        assert len(prompter.seen) == 1
        assert "hook wants confirmation" in prompter.seen[0].reason


# ============================================================================
# 4.5 边缘测试
# ============================================================================

class TestEdgeCases:

    def test_pp040_empty_policy(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        result = policy.authorize("unknown_tool", "{}")
        # Unknown tool defaults to danger-full-access requirement
        assert isinstance(result, DenyResult)

    def test_pp041_many_rules_performance(self):
        rules = [f"tool_{i:03d}(pattern_{i}:*)" for i in range(100)]
        policy = PermissionPolicy(
            PermissionMode.READ_ONLY, _default_tool_reqs(),
            allow_rules=rules,
        )
        import time
        start = time.monotonic()
        for _ in range(100):
            policy.authorize("tool_050", '{"command":"pattern_50 something"}')
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # 100 iterations < 100ms

    def test_pp042_invalid_rule_ignored(self):
        policy = PermissionPolicy(
            PermissionMode.DANGER_FULL_ACCESS, _default_tool_reqs(),
            deny_rules=["not a valid rule !!! )("],
        )
        # Should not crash — just treated as tool name match
        result = policy.authorize("bash", '{"command":"echo hi"}')
        assert isinstance(result, AllowResult)

    def test_pp044_mode_escalation(self):
        policy = PermissionPolicy(PermissionMode.WORKSPACE_WRITE, _default_tool_reqs())
        prompter = RecordingPrompter(allow=True)
        result = policy.authorize("bash", '{"command":"echo hi"}', prompter=prompter)
        assert isinstance(result, AllowResult)
        assert len(prompter.seen) == 1
        assert prompter.seen[0].current_mode == PermissionMode.WORKSPACE_WRITE
        assert prompter.seen[0].required_mode == PermissionMode.DANGER_FULL_ACCESS


# ============================================================================
# 4.6 故障注入
# ============================================================================

class TestFaultInjection:

    def test_pp050_prompter_exception(self):
        class BrokenPrompter:
            def decide(self, request):
                raise RuntimeError("prompter broken")
        policy = PermissionPolicy(PermissionMode.PROMPT, _default_tool_reqs())
        result = policy.authorize("bash", '{"command":"echo hi"}', prompter=BrokenPrompter())
        assert isinstance(result, DenyResult)

    def test_pp051_no_prompter_non_interactive(self):
        policy = PermissionPolicy(PermissionMode.PROMPT, _default_tool_reqs())
        result = policy.authorize("bash", '{"command":"echo hi"}')
        assert isinstance(result, DenyResult)

    def test_pp052_malicious_input(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, _default_tool_reqs())
        result = policy.authorize("read_file", '{"file_path":"' + "x" * 10000 + '"}')
        assert isinstance(result, AllowResult)


# ============================================================================
# Helper: policy_from_registry
# ============================================================================

class TestPolicyFromRegistry:

    def test_builds_correct_requirements(self):
        policy = policy_from_registry(
            PermissionMode.READ_ONLY,
            [("read_file", "read-only"), ("write_file", "workspace-write")],
        )
        assert isinstance(policy.authorize("read_file", "{}"), AllowResult)
        assert isinstance(policy.authorize("write_file", "{}"), DenyResult)
