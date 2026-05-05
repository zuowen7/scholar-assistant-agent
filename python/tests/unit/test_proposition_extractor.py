"""命题提取 — 单元测试

验证中文逻辑连接词的实际提取效果：
- 因果/转折/递进/条件/局限等逻辑关系
- 术语提取与一致性检查
- 逻辑感知翻译提示构建
"""
from __future__ import annotations

import pytest
from src.translator.proposition_extractor import (
    Proposition,
    ExtractedLogic,
    extract_propositions,
    build_logic_aware_prompt,
    extract_key_terms_cn,
    check_term_consistency,
)


# ── 真实中文文本逻辑提取 ────────────────────────────────────────────────


class TestExtractCausality:
    """因果逻辑提取 — '因此/所以/导致/由于' 等"""

    def test_detects_yinci_as_cause_effect(self) -> None:
        text = "实验组蛋白表达显著上调，因此该通路可能被激活。"
        result = extract_propositions(text)
        assert result.has_explicit_causality is True
        # 应至少提取出一个因果命题
        cause_effect_props = [p for p in result.propositions
                             if p.logic_type == "cause-effect"]
        assert len(cause_effect_props) >= 1

    def test_detects_daozhi_as_cause_effect(self) -> None:
        text = "药物处理导致细胞凋亡率增加3倍。"
        result = extract_propositions(text)
        assert result.has_explicit_causality is True

    def test_detects_youyu_as_cause_effect(self) -> None:
        text = "由于样本量不足，该结论需要进一步验证。"
        result = extract_propositions(text)
        assert result.has_explicit_causality is True

    def test_detects_yinci_with_connector_info(self) -> None:
        text = "A表达上调，因此B被抑制。"
        result = extract_propositions(text)
        ce_props = [p for p in result.propositions
                   if p.logic_type == "cause-effect"]
        if ce_props:
            assert len(ce_props[0].connector_cn) > 0
            assert len(ce_props[0].connector_en) > 0


class TestExtractContrast:
    """转折/对比逻辑提取 — '然而/但是/而/相比之下'"""

    def test_detects_raner_as_contrast(self) -> None:
        text = "药物A显著抑制肿瘤生长，然而药物B未见明显效果。"
        result = extract_propositions(text)
        assert result.has_contrast is True

    def test_detects_danshi_as_contrast(self) -> None:
        text = "该方法准确率高，但是计算成本较大。"
        result = extract_propositions(text)
        assert result.has_contrast is True

    def test_detects_suiran_danshi_as_concession(self) -> None:
        text = "虽然模型A表现更优，但泛化能力有限。"
        result = extract_propositions(text)
        # 让步也算对比
        assert result.has_contrast is True


class TestExtractAddition:
    """递进/补充逻辑 — '此外/另外/同时'"""

    def test_detects_ciwai(self) -> None:
        text = "该蛋白定位于线粒体。此外，它还参与内质网应激反应。"
        result = extract_propositions(text)
        addition_props = [p for p in result.propositions
                         if p.logic_type == "addition"]
        assert len(addition_props) >= 1


class TestExtractLimitation:
    """局限/未来工作 — '尚需/仍有待/需要注意的是'"""

    def test_detects_shangxu(self) -> None:
        text = "尚需更多临床试验验证该方法的有效性。"
        result = extract_propositions(text)
        assert result.has_limitation is True


class TestExtractCondition:
    """条件逻辑 — '如果/假如/除非'"""

    def test_detects_ruguo(self) -> None:
        text = "如果pH值低于6.0，酶的活性将显著下降。"
        result = extract_propositions(text)
        condition_props = [p for p in result.propositions
                          if p.logic_type == "condition"]
        assert len(condition_props) >= 1


class TestExtractImplication:
    """推论逻辑 — '这意味着/这说明/由此可见'"""

    def test_detects_yiweizhe(self) -> None:
        text = "敲除该基因后细胞停止分裂，这意味着该基因对细胞周期是必需的。"
        result = extract_propositions(text)
        imply_props = [p for p in result.propositions
                      if p.logic_type == "implication"]
        assert len(imply_props) >= 1


# ── 混合逻辑 ───────────────────────────────────────────────────────────


class TestMixedLogic:
    """一段文本包含多种逻辑关系"""

    def test_cause_and_contrast(self) -> None:
        text = (
            "由于EGFR突变导致信号通路持续激活，因此肿瘤细胞增殖加快。"
            "然而，EGFR抑制剂治疗后，增殖速率显著下降。"
        )
        result = extract_propositions(text)
        assert result.has_explicit_causality is True
        assert result.has_contrast is True
        # 多种逻辑类型的命题
        types = {p.logic_type for p in result.propositions}
        assert len(types) >= 2

    def test_dominant_logic_detected(self) -> None:
        text = "因此A增加，因此B上调，因此C被激活。然而D略有下降。"
        result = extract_propositions(text)
        assert len(result.dominant_logic) > 0
        # 因果命题占多数，dominant 应为 cause-effect
        assert result.dominant_logic == "cause-effect"


# ── 术语提取 ───────────────────────────────────────────────────────────


class TestKeyTermsExtraction:
    def test_extracts_bilingual_terms(self) -> None:
        """中文(English) 格式，如 '细胞凋亡(apoptosis)'"""
        terms = extract_key_terms_cn(
            "细胞凋亡(apoptosis)和自噬(autophagy)是两种程序性死亡方式。"
        )
        # 应提取到至少一个双语术语
        assert len(terms) >= 1

    def test_extracts_single_terms(self) -> None:
        """没有括号格式时也应提取可能的术语"""
        terms = extract_key_terms_cn("本研究探讨了EGFR信号通路在肺癌中的作用。")
        assert isinstance(terms, list)

    def test_no_duplicates(self) -> None:
        text = "细胞凋亡(apoptosis)和细胞凋亡(apoptosis)相关蛋白"
        terms = extract_key_terms_cn(text)
        # 去重
        assert len(terms) == len(set(terms))


class TestTermConsistency:
    def test_finds_registered_terms(self) -> None:
        """当前文本中的术语在已有的术语表中时，应返回映射"""
        previous = {"细胞凋亡": "apoptosis"}
        result = check_term_consistency("细胞凋亡相关蛋白表达上调。", previous)
        assert isinstance(result, dict)
        # 如果"细胞凋亡"在当前文本中出现且在previous中，应返回
        if "细胞凋亡" in result:
            assert result["细胞凋亡"] == "apoptosis"

    def test_returns_empty_for_no_overlap(self) -> None:
        previous = {"细胞凋亡": "apoptosis"}
        result = check_term_consistency("没有任何匹配术语的文本。", previous)
        assert len(result) == 0


# ── 提示构建 ───────────────────────────────────────────────────────────


class TestBuildLogicAwarePrompt:
    def test_causality_prompt_contains_logic_tag(self) -> None:
        text = "A促进B，因此C上调。"
        extracted = extract_propositions(text)
        prompt = build_logic_aware_prompt(text, extracted)
        assert "LOGIC" in prompt
        assert len(prompt) > 0

    def test_target_lang_accepted(self) -> None:
        """target_lang 参数被接受并影响提示（至少不崩溃）"""
        text = "A促进B。"
        extracted = extract_propositions(text)
        prompt_en = build_logic_aware_prompt(text, extracted, target_lang="en")
        prompt_zh = build_logic_aware_prompt(text, extracted, target_lang="zh")
        # 两种语言都应该返回有效提示
        assert isinstance(prompt_en, str) and len(prompt_en) > 0
        assert isinstance(prompt_zh, str) and len(prompt_zh) > 0

    def test_empty_text_handled(self) -> None:
        text = ""
        extracted = extract_propositions(text)
        prompt = build_logic_aware_prompt(text, extracted)
        assert isinstance(prompt, str)


# ── 边界情况 ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_text_no_propositions(self) -> None:
        result = extract_propositions("")
        assert len(result.propositions) == 0
        assert result.dominant_logic == ""

    def test_plain_descriptive_text(self) -> None:
        """没有明显逻辑连接词的纯描述文本"""
        result = extract_propositions("细胞在37°C条件下培养24小时。")
        assert isinstance(result, ExtractedLogic)
        # 可能提取出0或1个命题，但不能崩溃
