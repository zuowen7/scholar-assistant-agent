"""翻译客户端单元测试"""

from src.translator.ollama_client import (
    Glossary,
    TranslationResult,
    _extract_term_pairs,
    _repair_truncation,
    _strip_context_leak,
    _strip_preamble,
    _strip_think_tags,
    _validate_translation,
)


def _make_result(original: str, translated: str) -> TranslationResult:
    return TranslationResult(original=original, translated=translated, model="test")


# ── think 标签清理 ──


class TestStripThinkTags:
    def test_basic_think_tag(self) -> None:
        text = "<think >some reasoning</think >翻译结果"
        assert _strip_think_tags(text) == "翻译结果"

    def test_multiline_think_tag(self) -> None:
        text = "<think >\nline1\nline2\n</think >result"
        assert _strip_think_tags(text) == "result"

    def test_no_think_tag(self) -> None:
        text = "直接翻译结果"
        assert _strip_think_tags(text) == "直接翻译结果"

    def test_empty_after_strip(self) -> None:
        text = "<think >only thinking</think >"
        assert _strip_think_tags(text) == ""

    def test_redacted_thinking_tag(self) -> None:
        text = "<redacted_thinking>inner</redacted_thinking>正文"
        assert _strip_think_tags(text) == "正文"

    def test_multiple_think_tags(self) -> None:
        text = "<think >first</think >text1<think >second</think >text2"
        assert _strip_think_tags(text) == "text1text2"


# ── 前言清理 ──


class TestStripPreamble:
    def test_here_is_translation(self) -> None:
        text = "Here is the translation:\n你好世界"
        assert _strip_preamble(text) == "你好世界"

    def test_chinese_preamble(self) -> None:
        text = "以下是翻译：\n你好世界"
        assert _strip_preamble(text) == "你好世界"

    def test_translation_result_label_with_newline(self) -> None:
        text = "这是翻译结果\n你好世界"
        assert _strip_preamble(text) == "你好世界"

    def test_no_preamble(self) -> None:
        text = "这是翻译结果"
        assert _strip_preamble(text) == text

    def test_sure_here_is(self) -> None:
        text = "Sure, here is the translated text.\n你好"
        assert _strip_preamble(text) == "你好"

    def test_chinese_ok_prefix(self) -> None:
        text = "好的，以下是翻译：\n你好世界"
        assert _strip_preamble(text) == "你好世界"


# ── 上下文泄漏清理 ──


class TestStripContextLeak:
    def test_document_context_leak(self) -> None:
        text = "[文档背景（不要翻译此部分）]\nsome context\n\n实际翻译内容"
        assert "实际翻译内容" in _strip_context_leak(text)

    def test_translation_ref_leak(self) -> None:
        text = "[前文翻译参考（不要翻译此部分）]\nprevious\n\n翻译结果"
        assert "翻译结果" in _strip_context_leak(text)

    def test_no_leak(self) -> None:
        text = "正常翻译内容"
        assert _strip_context_leak(text) == text


# ── 截断修复 ──


class TestRepairTruncation:
    def test_truncated_chinese(self) -> None:
        """被截断的文本: 尾部残缺ASCII片段应被移除"""
        # 构造: 句号在文本前部, 后面跟大量已翻译内容(占满75%), 最后有残缺ASCII片段
        base = "这是一段完整的翻译。"
        # 中间插入足够的中文(让句号 > 75%)
        middle = "接下来的内容也翻译了。还有更多。最后一部分。"
        # 尾部残缺 ASCII 片段（不含 CJK，且长度 < 120）
        tail = "truncated fragment"
        text = base + middle + tail
        repaired = _repair_truncation(text)
        # 应至少保留到中间的句号
        assert "这是一段完整的翻译。" in repaired

    def test_no_truncation(self) -> None:
        text = "完整翻译结果。"
        assert _repair_truncation(text) == text

    def test_empty_string(self) -> None:
        assert _repair_truncation("") == ""

    def test_truncated_with_abbreviation(self) -> None:
        """不以缩写句号截断"""
        text = "See Fig. 3 for details"
        result = _repair_truncation(text)
        assert "Fig" in result


# ── 翻译结果校验 ──


class TestValidateTranslation:
    def test_valid_translation(self) -> None:
        r = _make_result("Hello world, this is a test.", "你好世界，这是一个测试。")
        assert _validate_translation(r) is True

    def test_empty_translation(self) -> None:
        r = _make_result("Hello world", "")
        assert _validate_translation(r) is False

    def test_too_short_translation(self) -> None:
        """长文本+超短译文: 应判定为无效"""
        r = _make_result("A" * 200, "短")
        assert _validate_translation(r) is False

    def test_identical_text(self) -> None:
        """长文本的译文与原文完全相同（去除空白后）时应判定为无效"""
        text = "This is exactly the same text that was given and it is long enough to pass the hundred character threshold for validation."
        r = _make_result(text, text)
        assert _validate_translation(r) is False

    def test_high_ascii_untranslated(self) -> None:
        """ASCII 占比过高且 CJK 构成少时应判定为未翻译"""
        orig = "A" * 150
        # trans 中全是 ASCII 字母（无空格无标点），ascii_ratio = 1.0 > 0.92，cjk_ratio = 0 < 0.12
        trans = "T" * 120 + "h" * 80 + "e" * 50
        r = _make_result(orig, trans)
        assert _validate_translation(r) is False

    def test_short_text_passes(self) -> None:
        """短文本（< 100 chars）只要有输出就通过"""
        r = _make_result("Title", "标题")
        assert _validate_translation(r) is True

    def test_latex_heavy_passes(self) -> None:
        """含大量 LaTeX 的原文，降低长度要求"""
        r = _make_result(
            r"$E = mc^2$ and $\sum_{i=1}^{n} x_i = n\bar{x}$ with ${a \over b}$",
            r"$E = mc^2$ 与 $\sum_{i=1}^{n} x_i = n\bar{x}$ 其中 ${a \over b}$",
        )
        assert _validate_translation(r) is True


# ── 术语表 ──


class TestGlossary:
    def test_empty_glossary(self) -> None:
        g = Glossary()
        assert g.to_prompt_text() == ""

    def test_update_and_retrieve(self) -> None:
        g = Glossary()
        g.update("phylogenetics", "系统发育学（phylogenetics）")
        text = g.to_prompt_text()
        assert "phylogenetics" in text
        assert "系统发育学" in text

    def test_deduplication(self) -> None:
        g = Glossary()
        g.update("phylogenetics", "系统发育学（phylogenetics）")
        g.update("phylogenetics", "系统发育学（phylogenetics）")
        text = g.to_prompt_text()
        assert text.count("phylogenetics") == 1

    def test_max_terms_limit(self) -> None:
        g = Glossary()
        for i in range(50):
            g.update(f"term{ i}", f"术语{i}（term{i}）")
        text = g.to_prompt_text()
        lines = [l for l in text.split("\n") if l.strip()]
        assert len(lines) <= 30


# ── 术语提取 ──


class TestExtractTermPairs:
    def test_basic_pair(self) -> None:
        pairs = _extract_term_pairs(
            "phylogenetics analysis",
            "系统发育学（phylogenetics）分析",
        )
        assert len(pairs) >= 1
        assert pairs[0][0] == "phylogenetics"
        assert pairs[0][1] == "系统发育学"

    def test_no_pairs(self) -> None:
        pairs = _extract_term_pairs("normal text", "正常文本")
        assert pairs == []

    def test_multiple_pairs(self) -> None:
        pairs = _extract_term_pairs(
            "phylogenetics and genomics",
            "系统发育学（phylogenetics）和基因组学（genomics）研究",
        )
        assert len(pairs) >= 2
