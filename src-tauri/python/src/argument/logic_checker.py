"""Argument Mapping — 确定性规则引擎（不调用 LLM）

5 类检查项:
1. 链路完整性 — 经典论证链条是否存在（问题→建模→分析→验证→结论）
2. 术语定义 — 引入的术语是否在树中某节点定义过
3. 引用闭环 — 挂载了文献的节点是否在下游有对应结论
4. 逻辑跳跃 — 相邻节点间是否缺乏过渡节点
5. 领域覆盖 — 根据 domain_tags 检查是否覆盖领域必备节点
"""

from __future__ import annotations

import logging
import re

from src.argument.models import ArgumentNode, ArgumentTree, IssueSeverity, RuleIssue

logger = logging.getLogger(__name__)

# 经典论证链关键词映射
_CLASSIC_CHAIN_KEYWORDS: dict[str, list[str]] = {
    "problem": ["问题", "背景", "挑战", "problem", "challenge", "background", "issue", "现状", "需求"],
    "modeling": ["建模", "模型", "model", "modeling", "框架", "framework", "体系", "结构设计", "数学模型"],
    "analysis": ["分析", "analysis", "评估", "evaluation", "研究", "study", "稳定性", "性能", "方法"],
    "verification": ["验证", "实验", "仿真", "simulation", "experiment", "verification", "测试", "对比"],
    "conclusion": ["结论", "总结", "conclusion", "summary", "展望", "future", "讨论"],
}


# 领域必备节点标签
_DOMAIN_REQUIRED_TAGS: dict[str, list[str]] = {
    "control_theory": ["simulation", "stability", "modeling"],
    "machine_learning": ["dataset", "evaluation", "baseline"],
    "nlp": ["dataset", "evaluation", "model"],
}

# 领域必备关键词
_DOMAIN_REQUIRED_KEYWORDS: dict[str, list[str]] = {
    "control_theory": ["仿真", "验证", "稳定性分析", "对比实验"],
    "machine_learning": ["数据集", "评估指标", "基线对比"],
}


class LogicChecker:
    """确定性规则引擎 — 对节点树做结构性扫描，返回 RuleIssue 列表。"""

    def check(self, tree: ArgumentTree, node_ids: list[str] | None = None) -> list[RuleIssue]:
        """执行全部规则检查。

        Args:
            tree: 完整的节点树。
            node_ids: 仅检查这些节点（及其子树）。None 表示检查全树。

        Returns:
            规则引擎识别到的所有问题。
        """
        target_nodes = self._resolve_nodes(tree, node_ids)
        if not target_nodes:
            return []

        issues: list[RuleIssue] = []
        issues.extend(self._check_chain_integrity(tree, target_nodes))
        issues.extend(self._check_term_definitions(tree, target_nodes))
        issues.extend(self._check_reference_closure(tree, target_nodes))
        issues.extend(self._check_logic_jumps(tree, target_nodes))
        issues.extend(self._check_domain_coverage(tree, target_nodes))
        return issues

    def _resolve_nodes(self, tree: ArgumentTree, node_ids: list[str] | None) -> list[ArgumentNode]:
        if node_ids is None:
            return list(tree.nodes.values())
        return [tree.nodes[nid] for nid in node_ids if nid in tree.nodes]

    # ── Rule 1: 链路完整性 ────────────────────────────────────────

    def _check_chain_integrity(self, tree: ArgumentTree, nodes: list[ArgumentNode]) -> list[RuleIssue]:
        if not nodes:
            return []

        issues: list[RuleIssue] = []
        all_text = " ".join(f"{n.topic} {n.content}" for n in nodes)

        missing_chains: list[str] = []
        for chain_name, keywords in _CLASSIC_CHAIN_KEYWORDS.items():
            if not any(kw.lower() in all_text.lower() for kw in keywords):
                missing_chains.append(chain_name)

        if missing_chains:
            root_id = tree.root_id or ""
            issues.append(RuleIssue(
                issue_code="MISSING_CLASSIC_CHAIN",
                severity=IssueSeverity.warning,
                node_ids=[root_id] if root_id in tree.nodes else [],
                description=f"论文论证链缺少以下环节: {', '.join(missing_chains)}",
                suggestion=f"建议补充以下章节节点: {', '.join(missing_chains)}",
            ))
        return issues

    # ── Rule 2: 术语定义 ──────────────────────────────────────────

    def _check_term_definitions(self, tree: ArgumentTree, nodes: list[ArgumentNode]) -> list[RuleIssue]:
        issues: list[RuleIssue] = []
        all_node_texts = {
            nid: f"{n.topic} {n.content}".lower()
            for nid, n in tree.nodes.items()
        }

        for node in nodes:
            # 简易术语提取：大写缩写（3+字母）和专业术语模式
            abbreviations = re.findall(r'\b[A-Z]{3,}\b', node.topic + " " + node.content)
            for abbr in abbreviations:
                # 检查是否有其他节点定义了这个术语
                defined = any(
                    f"{abbr.lower()}" in text and nid != node.id
                    for nid, text in all_node_texts.items()
                )
                if not defined:
                    issues.append(RuleIssue(
                        issue_code="UNDEFINED_TERM",
                        severity=IssueSeverity.error,
                        node_ids=[node.id],
                        description=f"节点「{node.topic}」中使用了未定义术语: {abbr}",
                        suggestion=f"建议在合适的位置添加对 {abbr} 的定义或说明",
                    ))
        return issues

    # ── Rule 3: 引用闭环 ──────────────────────────────────────────

    def _check_reference_closure(self, tree: ArgumentTree, nodes: list[ArgumentNode]) -> list[RuleIssue]:
        issues: list[RuleIssue] = []

        for node in nodes:
            if not node.references:
                continue

            # 检查该节点是否有子节点或下游节点引用了该文献的结论
            has_conclusion = False
            stack = list(node.children)
            while stack:
                child_id = stack.pop()
                child = tree.nodes.get(child_id)
                if child:
                    child_text = f"{child.topic} {child.content}".lower()
                    for ref in node.references:
                        key_parts = re.findall(r'[A-Za-z]+', ref.citation_key)
                        if any(part.lower() in child_text for part in key_parts if len(part) > 2):
                            has_conclusion = True
                            break
                    stack.extend(child.children)
                if has_conclusion:
                    break

            if not has_conclusion and node.children:
                issues.append(RuleIssue(
                    issue_code="ORPHAN_REFERENCE",
                    severity=IssueSeverity.warning,
                    node_ids=[node.id],
                    description=f"节点「{node.topic}」挂载了文献但下游未见对应结论",
                    suggestion="建议在子节点中补充基于所挂载文献的分析或结论",
                ))
        return issues

    # ── Rule 4: 逻辑跳跃 ──────────────────────────────────────────

    def _check_logic_jumps(self, tree: ArgumentTree, nodes: list[ArgumentNode]) -> list[RuleIssue]:
        issues: list[RuleIssue] = []

        for node in nodes:
            if not node.children or node.depth == 0:
                continue

            child_nodes = [tree.nodes[cid] for cid in node.children if cid in tree.nodes]
            if len(child_nodes) < 2:
                continue

            # 提取语义单元：英文单词 + 中文 2-gram 滑动窗口
            parent_tokens = self._extract_semantic_tokens(node.topic)
            if not parent_tokens:
                continue

            for child in child_nodes:
                child_tokens = self._extract_semantic_tokens(child.topic)
                overlap = parent_tokens & child_tokens
                if not overlap:
                    issues.append(RuleIssue(
                        issue_code="LOGIC_JUMP",
                        severity=IssueSeverity.warning,
                        node_ids=[child.id],
                        related_nodes=[node.id],
                        description=f"节点「{child.topic}」与父节点「{node.topic}」可能存在逻辑跳跃",
                        suggestion="建议补充过渡节点或调整节点关系",
                    ))
        return issues

    @staticmethod
    def _extract_semantic_tokens(text: str) -> set[str]:
        """提取文本的语义单元：英文单词 + 中文 2-gram。"""
        tokens: set[str] = set()
        lower = text.lower()
        # 英文单词
        for w in re.findall(r'[a-zA-Z]{2,}', lower):
            tokens.add(w)
        # 中文 2-gram 滑动窗口
        cjk = re.findall(r'[一-鿿]+', text)
        for segment in cjk:
            for i in range(len(segment) - 1):
                tokens.add(segment[i:i + 2])
        return tokens

    # ── Rule 5: 领域覆盖 ──────────────────────────────────────────

    def _check_domain_coverage(self, tree: ArgumentTree, nodes: list[ArgumentNode]) -> list[RuleIssue]:
        issues: list[RuleIssue] = []

        # 收集所有 domain_tags
        all_tags: set[str] = set()
        for node in nodes:
            all_tags.update(node.domain_tags)

        for domain, required_tags in _DOMAIN_REQUIRED_TAGS.items():
            if domain not in all_tags:
                continue

            missing = [tag for tag in required_tags if tag not in all_tags]
            if not missing:
                continue

            root_id = tree.root_id or ""

            required_keywords = _DOMAIN_REQUIRED_KEYWORDS.get(domain, [])
            all_text = " ".join(f"{n.topic} {n.content}" for n in nodes).lower()
            missing_keywords = [
                kw for kw in required_keywords
                if kw.lower() not in all_text
            ]

            if missing_keywords:
                issues.append(RuleIssue(
                    issue_code="DOMAIN_GAP",
                    severity=IssueSeverity.warning,
                    node_ids=[root_id] if root_id in tree.nodes else [],
                    description=f"领域 {domain} 缺少必要节点: {', '.join(missing_keywords)}",
                    suggestion=f"建议增加以下节点: {', '.join(missing_keywords)}",
                ))
        return issues
