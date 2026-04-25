"""Argument Mapping — 反馈文字生成器

接受规则引擎的 RuleIssue 列表，通过 LLM 生成自然的学术语言反馈。
Agent 的职责仅限于润色文字，输出受规则诊断结果的约束。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.argument.models import ArgumentTree, IssueSeverity, LogicStatus, RuleIssue

logger = logging.getLogger(__name__)

_FEEDBACK_PROMPT = """你是一位学术论文逻辑审查助手。根据以下结构化的规则引擎诊断结果，为每个节点生成简洁的自然语言反馈。

诊断结果:
{rule_results}

节点信息:
{node_info}

要求:
1. 为每个有问题的节点生成一句自然的反馈（中文学术风格）
2. 反馈应当指出问题和建议，语气友好但专业
3. 只输出 JSON 格式: {{"node_id": "反馈文字"}}
4. 不要输出任何其他内容"""


def _build_node_info(tree: ArgumentTree, node_ids: list[str]) -> str:
    lines = []
    for nid in node_ids:
        node = tree.nodes.get(nid)
        if node:
            lines.append(f"- {nid}: topic='{node.topic}', depth={node.depth}, refs={len(node.references)}")
    return "\n".join(lines)


def _build_rule_summary(issues: list[RuleIssue]) -> str:
    lines = []
    for issue in issues:
        lines.append(
            f"[{issue.issue_code}] ({issue.severity.value}) "
            f"nodes={issue.node_ids} | {issue.description}"
        )
    return "\n".join(lines)


class FeedbackGenerator:
    """基于规则引擎诊断结果生成自然语言反馈。"""

    async def generate(
        self,
        tree: ArgumentTree,
        issues: list[RuleIssue],
        cloud_client: Any = None,
        ollama_client: Any = None,
    ) -> dict[str, dict[str, Any]]:
        """为有问题的节点生成自然语言反馈。

        Args:
            tree: 节点树。
            issues: 规则引擎诊断出的问题列表。
            cloud_client: CloudClient（优先使用）。
            ollama_client: OllamaClient（fallback）。

        Returns:
            dict: node_id → {logic_status, rule_issues, agent_feedback}
        """
        if not issues:
            # 全部通过
            return {}

        # 收集涉及的节点 ID
        affected_node_ids: set[str] = set()
        for issue in issues:
            affected_node_ids.update(issue.node_ids)

        # 尝试调用 LLM 生成反馈
        feedback_map: dict[str, str] = {}
        try:
            raw = await self._call_llm(
                _FEEDBACK_PROMPT.format(
                    rule_results=_build_rule_summary(issues),
                    node_info=_build_node_info(tree, list(affected_node_ids)),
                ),
                cloud_client,
                ollama_client,
            )
            if raw:
                feedback_map = self._parse_feedback(raw)
        except Exception as e:
            logger.warning("LLM 反馈生成失败，使用规则引擎原始描述: %s", e)

        # 组装结果
        result: dict[str, dict[str, Any]] = {}
        for nid in affected_node_ids:
            node = tree.nodes.get(nid)
            if not node:
                continue

            # 收集该节点的 issues
            node_issues = [iss for iss in issues if nid in iss.node_ids]
            issue_codes = [iss.issue_code for iss in node_issues]

            # 确定逻辑状态
            severities = [iss.severity for iss in node_issues]
            if IssueSeverity.error in severities:
                logic_status = LogicStatus.error
            elif IssueSeverity.warning in severities:
                logic_status = LogicStatus.warning
            else:
                logic_status = LogicStatus.pass_

            # 反馈文字：LLM 生成 > 规则引擎 description > None
            feedback = feedback_map.get(nid)
            if not feedback and node_issues:
                feedback = node_issues[0].description

            result[nid] = {
                "logic_status": logic_status.value,
                "rule_issues": issue_codes,
                "agent_feedback": feedback,
            }

        return result

    def generate_sync(self, tree: ArgumentTree, issues: list[RuleIssue]) -> dict[str, dict[str, Any]]:
        """同步版本 — 不调用 LLM，直接使用规则引擎描述。"""
        result: dict[str, dict[str, Any]] = {}
        for issue in issues:
            for nid in issue.node_ids:
                if nid not in result:
                    node = tree.nodes.get(nid)
                    if not node:
                        continue
                    result[nid] = {
                        "logic_status": LogicStatus.warning.value,
                        "rule_issues": [],
                        "agent_feedback": None,
                    }
                result[nid]["rule_issues"].append(issue.issue_code)

                if issue.severity == IssueSeverity.error:
                    result[nid]["logic_status"] = LogicStatus.error.value
                elif result[nid]["logic_status"] != LogicStatus.error.value:
                    result[nid]["logic_status"] = LogicStatus.warning.value

                if not result[nid]["agent_feedback"]:
                    result[nid]["agent_feedback"] = issue.description
        return result

    async def _call_llm(self, prompt: str, cloud_client: Any = None, ollama_client: Any = None) -> str:
        from src.argument.llm_client import call_llm_chat
        return await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.5)

    def _parse_feedback(self, raw: str) -> dict[str, str]:
        """解析 LLM 输出的 node_id→feedback 映射。"""
        import re

        text = raw.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return {}
