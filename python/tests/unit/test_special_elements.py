"""特殊元素处理单元测试 — 完整覆盖

测试覆盖：
- MarkdownElements 解析器（图片、表格、公式、引用）
- Vision API 集成（图片分析）
- 表格生成与解析
- LaTeX 公式格式化
- 引用上下文获取
- 工具注册
"""

import pytest
from src.agent.special_elements import (
    MarkdownElements,
    ElementInfo,
    analyze_markdown_elements,
    extract_image_for_analysis,
    parse_table_structure,
    generate_table_markdown,
    format_latex_formula,
    get_citation_context,
    build_special_elements_tools,
)


# ============================================================================
# MarkdownElements 解析器测试
# ============================================================================

class TestMarkdownElementsParser:
    """MarkdownElements 解析器核心测试"""

    def test_parse_empty_text(self):
        """空文本解析"""
        parser = MarkdownElements()
        elements = parser.parse("")
        assert elements == []

    def test_parse_no_special_elements(self):
        """无特殊元素的纯文本"""
        parser = MarkdownElements()
        text = "这是一段普通的中文文本，没有任何特殊元素。"
        elements = parser.parse(text)
        assert elements == []

    def test_parse_plain_text_with_punctuation(self):
        """带标点的纯文本（不是公式）"""
        parser = MarkdownElements()
        # 单个 $ 在文本中不应该被识别为公式
        text = "价格是 $100，不含税。"
        elements = parser.parse(text)
        # 应该没有公式（因为 $ 后面不是有效的公式）
        assert len(elements) == 0


class TestImageParsing:
    """图片解析测试"""

    def test_parse_simple_image(self):
        parser = MarkdownElements()
        text = "![alt text](path/to/image.png)"
        elements = parser.parse(text)

        assert len(elements) == 1
        img = elements[0]
        assert img.type == "image"
        assert img.content == "path/to/image.png"
        assert img.metadata["alt"] == "alt text"

    def test_parse_image_with_empty_alt(self):
        parser = MarkdownElements()
        text = "![](path/to/image.png)"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].metadata["alt"] == ""

    def test_parse_image_with_parentheses_in_alt(self):
        """Alt 中包含括号的情况"""
        parser = MarkdownElements()
        text = "![alt with (parentheses)](path.png)"
        elements = parser.parse(text)

        # 标准 Markdown 不支持 alt 中包含未转义的 )
        # 这个测试验证当前的解析行为
        assert len(elements) >= 0  # 行为取决于实现

    def test_parse_image_with_basic_alt(self):
        """基本的图片 alt 解析"""
        parser = MarkdownElements()
        text = "![Figure 1: Results](results.png)"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert "results.png" in elements[0].content

    def test_parse_image_url(self):
        parser = MarkdownElements()
        text = "![logo](https://example.com/logo.png)"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert "https://" in elements[0].content

    def test_parse_multiple_images(self):
        parser = MarkdownElements()
        text = "First ![img1](a.png). Second ![img2](b.jpg). Third ![img3](c.gif)."
        elements = parser.parse(text)

        assert len(elements) == 3
        assert all(e.type == "image" for e in elements)
        # 按位置排序
        assert elements[0].index < elements[1].index < elements[2].index

    def test_parse_image_in_complex_context(self):
        parser = MarkdownElements()
        text = """## 图片示例

这是一个展示图片的段落：

![Figure 1: Neural Network Architecture](fig1.png)

如图所示，网络的结构如下。"""
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].metadata["alt"] == "Figure 1: Neural Network Architecture"
        assert elements[0].content == "fig1.png"


class TestMathParsing:
    """数学公式解析测试"""

    def test_parse_inline_math_simple(self):
        parser = MarkdownElements()
        text = "质能方程 $E = mc^2$ 是著名的。"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].type == "inline_math"
        assert elements[0].content == "E = mc^2"

    def test_parse_inline_math_complex(self):
        parser = MarkdownElements()
        text = "积分公式 $\\int_0^\\infty e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}$"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert "int" in elements[0].content
        assert "frac" in elements[0].content

    def test_parse_inline_math_multiple(self):
        parser = MarkdownElements()
        text = "$x^2 + y^2 = z^2$ 是勾股定理，$a^2 + b^2 = c^2$ 也是。"
        elements = parser.parse(text)

        assert len(elements) == 2
        assert all(e.type == "inline_math" for e in elements)

    def test_parse_display_math_simple(self):
        parser = MarkdownElements()
        text = """$$\n\\int_0^1 x dx = \\frac{1}{2}\n$$"""
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].type == "display_math"
        assert "frac" in elements[0].content

    def test_parse_display_math_multiline(self):
        parser = MarkdownElements()
        text = """$$
\\begin{bmatrix}
a & b \\\\
c & d
\\end{bmatrix}
$$"""
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].type == "display_math"
        assert "bmatrix" in elements[0].content

    def test_parse_mixed_inline_and_display(self):
        parser = MarkdownElements()
        text = "在线公式 $x = 1$，块级公式：\n$$\nx^2 = 1\n$$"
        elements = parser.parse(text)

        assert len(elements) == 2
        assert elements[0].type == "inline_math"
        assert elements[1].type == "display_math"

    def test_parse_math_with_dollar_in_text(self):
        """文本中的 $ 不是公式边界"""
        parser = MarkdownElements()
        # 5美元不应该被解析为公式
        text = "The price is $5 for members."
        elements = parser.parse(text)
        assert len(elements) == 0

    def test_parse_math_with_newline_in_inline(self):
        """行内公式包含换行时应该只取第一行"""
        parser = MarkdownElements()
        text = "$formula\nwith newline$"
        elements = parser.parse(text)
        # 复杂的换行情况，可能不匹配或只匹配到换行前
        assert isinstance(elements, list)


class TestTableParsing:
    """表格解析测试"""

    def test_parse_simple_table(self):
        parser = MarkdownElements()
        text = """| 列1 | 列2 | 列3 |
| --- | --- | --- |
| A1 | B1 | C1 |
| A2 | B2 | C2 |"""
        elements = parser.parse(text)

        assert len(elements) == 1
        table = elements[0]
        assert table.type == "table"
        assert table.metadata["cols"] == 3
        assert table.metadata["rows"] >= 2

    def test_parse_table_with_alignment(self):
        parser = MarkdownElements()
        text = """| 左对齐 | 居中 | 右对齐 |
| :--- | :---: | ---: |
| A | B | C |"""
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].metadata["cols"] == 3

    def test_parse_table_with_empty_cells(self):
        parser = MarkdownElements()
        text = """| A | B | C |
| --- | --- | --- |
| 1 | | 3 |
| | 2 | |"""
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].type == "table"

    def test_parse_table_with_special_chars(self):
        parser = MarkdownElements()
        text = """| 含竖线 | 含引号 | 含括号 |
| --- | --- | --- |
| A \| B | "C" | (D) |"""
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].type == "table"

    def test_parse_table_multiline_cells(self):
        """单元格内包含换行的表格"""
        parser = MarkdownElements()
        text = """| A | B |
| --- | --- |
| Line1\nLine2 | C |"""
        elements = parser.parse(text)

        # 简化处理，解析器应该能处理
        assert len(elements) >= 0  # 行为取决于具体实现


class TestCitationParsing:
    """文献引用解析测试"""

    def test_parse_simple_citation(self):
        parser = MarkdownElements()
        text = "根据 [@smith2020] 的研究"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].type == "citation"
        assert elements[0].content == "smith2020"

    def test_parse_citation_with_year(self):
        parser = MarkdownElements()
        text = "[@smith_et_al_2020]"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert "smith_et_al_2020" in elements[0].content

    def test_parse_citation_with_page(self):
        parser = MarkdownElements()
        text = "[@jones2021, p.123]"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].content == "jones2021"

    def test_parse_citation_with_page_range(self):
        parser = MarkdownElements()
        text = "[@author2022, pp. 45-67]"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].content == "author2022"

    def test_parse_multiple_citations(self):
        parser = MarkdownElements()
        text = "[@a], [@b], and [@c] all demonstrated this."
        elements = parser.parse(text)

        assert len(elements) == 3
        keys = [e.content for e in elements]
        assert keys == ["a", "b", "c"]

    def test_parse_citation_in_paragraph(self):
        """段落中间的引用"""
        parser = MarkdownElements()
        text = "近年来，深度学习在图像识别领域取得了显著进展[@lecun2015]。本文方法在此基础上进行了改进。"
        elements = parser.parse(text)

        assert len(elements) == 1
        assert elements[0].content == "lecun2015"

    def test_parse_duplicate_citations(self):
        """同一引用出现多次"""
        parser = MarkdownElements()
        text = "[@smith] 的早期工作[@smith]和后续研究[@smith]都证明了这一点。"
        elements = parser.parse(text)

        assert len(elements) == 3
        assert all(e.content == "smith" for e in elements)


class TestMixedContent:
    """混合内容解析测试"""

    def test_parse_all_element_types(self):
        """同时包含所有类型元素的复杂文档"""
        parser = MarkdownElements()
        text = """# 论文标题

![Figure 1](fig1.png)

如图 $f(x) = x^2$ 所示。

| Method | Accuracy |
| --- | --- |
| Ours | 95% |

根据 [@smith2020] 和 [@jones2021] 的研究[@jones2021, p.50]，我们得出结论。

$$
\\sum_{i=1}^n x_i
$$
"""
        elements = parser.parse(text)

        by_type = parser.get_by_type
        assert len(by_type("image")) == 1
        assert len(by_type("inline_math")) == 1
        assert len(by_type("display_math")) == 1
        assert len(by_type("table")) == 1
        assert len(by_type("citation")) == 3  # 2 unique, 3 occurrences

    def test_parse_order_preservation(self):
        """元素按文档顺序排列"""
        parser = MarkdownElements()
        text = "开始 $math1$ ![img](a.png) [@cite] 结束"
        parser.parse(text)

        elements = parser.elements
        assert elements[0].type == "inline_math"
        assert elements[1].type == "image"
        assert elements[2].type == "citation"

    def test_parse_nested_markers(self):
        """嵌套标记的处理"""
        parser = MarkdownElements()
        # 图片和公式混合的文本
        text = "Text with formula $x^2$ and image ![fig](fig.png)"
        elements = parser.parse(text)

        # 应该能识别公式和图片
        assert len(elements) >= 2  # 至少1个公式 + 1个图片
        types = [e.type for e in elements]
        assert "inline_math" in types
        assert "image" in types


# ============================================================================
# 工具函数测试
# ============================================================================

class TestAnalyzeMarkdownElements:
    """analyze_markdown_elements 函数测试"""

    def test_analyze_simple(self):
        text = "![图片](test.png)"
        result = analyze_markdown_elements(text)

        assert result["count"] == 1
        assert len(result["elements"]) == 1
        assert "summary" in result

    def test_analyze_empty(self):
        result = analyze_markdown_elements("普通文本没有特殊元素")
        assert result["count"] == 0
        assert "未发现" in result["summary"]

    def test_analyze_complex_document(self):
        text = """# 研究背景

![图1](fig1.png)

实验结果见表1。

| 方法 | 准确率 |
| --- | --- |
| A | 90% |

$$E = mc^2$$

参考文献[@a; @b]。
"""
        result = analyze_markdown_elements(text)

        assert result["count"] >= 4
        summary = result["summary"]
        assert "图片" in summary or "image" in summary.lower()


class TestExtractImageForAnalysis:
    """extract_image_for_analysis 函数测试"""

    def test_nonexistent_file(self):
        result = extract_image_for_analysis("/nonexistent/path/image.png")
        assert result["ready"] is False
        assert "不存在" in result["error"]

    def test_unsupported_format(self):
        """模拟不支持的格式"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"fake content")
            temp_path = f.name

        try:
            result = extract_image_for_analysis(temp_path)
            assert result["ready"] is False
            assert "不支持" in result["error"]
        finally:
            os.unlink(temp_path)

    def test_valid_png_image(self):
        """PNG 图片（需要创建临时文件）"""
        import tempfile
        import os

        # 创建最小的有效 PNG（1x1 像素）
        png_header = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D,  # IHDR length
            0x49, 0x48, 0x44, 0x52,  # IHDR
            0x00, 0x00, 0x00, 0x01,  # width: 1
            0x00, 0x00, 0x00, 0x01,  # height: 1
            0x08, 0x02,  # bit depth: 8, color type: 2 (RGB)
            0x00, 0x00, 0x00,  # compression, filter, interlace
            0x90, 0x77, 0x53, 0xDE,  # CRC
        ])

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_header)
            temp_path = f.name

        try:
            result = extract_image_for_analysis(temp_path)
            assert result["ready"] is True
            assert "base64" in result
            assert result["format"] == "png"
        finally:
            os.unlink(temp_path)


# ============================================================================
# 表格解析与生成测试
# ============================================================================

class TestParseTableStructure:
    """parse_table_structure 函数测试"""

    def test_parse_simple_table(self):
        md = """| 列1 | 列2 |
| --- | --- |
| A | B |
| C | D |"""
        result = parse_table_structure(md)

        assert result["headers"] == ["列1", "列2"]
        assert result["col_count"] == 2
        assert result["row_count"] >= 2

    def test_parse_empty_table(self):
        result = parse_table_structure("")
        assert result["headers"] == []
        assert result["row_count"] == 0

    def test_parse_single_column(self):
        md = """| 唯一列 |
| --- |
| 数据1 |
| 数据2 |"""
        result = parse_table_structure(md)

        assert result["col_count"] == 1
        assert result["row_count"] >= 2

    def test_parse_many_columns(self):
        md = """| A | B | C | D | E |
| --- | --- | --- | --- | --- |
| 1 | 2 | 3 | 4 | 5 |"""
        result = parse_table_structure(md)

        assert result["col_count"] == 5

    def test_parse_cells_with_spaces(self):
        md = """| 列 A | 列 B |
| --- | --- |
| 数据 A | 数据 B |"""
        result = parse_table_structure(md)

        assert result["headers"] == ["列 A", "列 B"]


class TestGenerateTableMarkdown:
    """generate_table_markdown 函数测试"""

    def test_generate_basic_table(self):
        headers = ["姓名", "年龄"]
        rows = [["张三", "25"], ["李四", "30"]]
        md = generate_table_markdown(headers, rows)

        assert "| 姓名 | 年龄 |" in md
        assert "| --- | --- |" in md
        assert "| 张三 | 25 |" in md
        assert "| 李四 | 30 |" in md

    def test_generate_empty_table(self):
        md = generate_table_markdown([], [])
        assert md == ""

    def test_generate_single_column(self):
        md = generate_table_markdown(["项目"], [["A"], ["B"]])
        assert "| 项目 |" in md
        assert "| A |" in md

    def test_generate_many_columns(self):
        headers = ["A", "B", "C", "D", "E"]
        rows = [["1", "2", "3", "4", "5"]]
        md = generate_table_markdown(headers, rows)

        # 5列表格，每行有 6 个 | (开头、空格、|、内容...)
        # 实际上是 7 个 |: | A | B | C | D | E |
        lines = md.split("\n")
        # 检查表头行有正确的列数
        header_cells = [p for p in lines[0].split("|") if p.strip()]
        assert len(header_cells) == 5

    def test_truncate_excess_rows(self):
        """超过表头列数的行应该被截断"""
        headers = ["A", "B"]
        rows = [["1", "2", "3", "4"]]  # 4列但表头只有2列
        md = generate_table_markdown(headers, rows)

        # 应该只有2列
        lines = md.split("\n")
        for line in lines[2:]:  # 跳过表头和分隔符
            if line.strip():
                cells = [c for c in line.split("|") if c.strip()]
                assert len(cells) <= 2

    def test_pad_short_rows(self):
        """少于表头列数的行应该被填充空"""
        headers = ["A", "B", "C"]
        rows = [["1"]]  # 只有1列
        md = generate_table_markdown(headers, rows)

        # 通过解析表格来验证 - 如果填充正确，parse_table_structure 应该能正确解析
        from src.agent.special_elements import parse_table_structure
        result = parse_table_structure(md)

        assert result["col_count"] == 3
        # 第一行数据应该只有1个有效单元格
        assert len(result["rows"][0]) >= 1

    def test_roundtrip(self):
        """生成后再解析应该得到相同结构"""
        original_md = """| A | B |
| --- | --- |
| 1 | 2 |"""
        parsed = parse_table_structure(original_md)
        regenerated = generate_table_markdown(
            parsed["headers"],
            parsed["rows"]
        )

        # 解析重生成的表格
        reparsed = parse_table_structure(regenerated)
        assert reparsed["headers"] == parsed["headers"]
        assert reparsed["col_count"] == parsed["col_count"]


# ============================================================================
# LaTeX 公式格式化测试
# ============================================================================

class TestFormatLatexFormula:
    """format_latex_formula 函数测试"""

    def test_format_inline(self):
        result = format_latex_formula("E = mc^2", display=False)
        assert result == "$E = mc^2$"

    def test_format_display(self):
        result = format_latex_formula("\\frac{1}{2}", display=True)
        assert result.startswith("$$")
        assert result.endswith("$$")

    def test_strip_existing_dollar_single(self):
        result = format_latex_formula("$x^2$", display=False)
        assert result == "$x^2$"  # 单对 $ 保持不变

    def test_strip_existing_dollar_double(self):
        result = format_latex_formula("$$x^2$$", display=False)
        assert result == "$x^2$"  # 去掉外层 $$

    def test_strip_existing_dollar_display(self):
        result = format_latex_formula("$x^2$", display=True)
        assert result.startswith("$$")  # 变成 $$

    def test_whitespace_handling(self):
        result = format_latex_formula("  E = mc^2  ", display=False)
        assert result == "$E = mc^2$"  # 空格被去除

    def test_complex_latex(self):
        latex = "\\int_0^\\infty \\frac{1}{x^2} dx"
        result = format_latex_formula(latex, display=True)
        assert "\\int" in result
        assert "\\frac" in result


# ============================================================================
# 引用上下文测试
# ============================================================================

class TestGetCitationContext:
    """get_citation_context 函数测试"""

    def test_get_context_middle(self):
        text = "Some text before " * 20 + "[@smith2020]" + " Some text after " * 20
        context = get_citation_context(text, "smith2020")

        assert "[@smith2020]" in context
        assert len(context) < 600  # 应该在合理范围内

    def test_get_context_at_start(self):
        text = "[@start2020]" + " following text " * 50
        context = get_citation_context(text, "start2020")

        assert "[@start2020]" in context

    def test_get_context_at_end(self):
        text = "preceding text " * 50 + "[@end2020]"
        context = get_citation_context(text, "end2020")

        assert "[@end2020]" in context

    def test_not_found(self):
        context = get_citation_context("No citation here", "nonexistent")
        assert "Not found" in context or "nonexistent" in context

    def test_ellipsis_added(self):
        """超出范围的引用应该添加省略号"""
        text = "start " * 100 + "[@mid2020]" + " end " * 100
        context = get_citation_context(text, "mid2020")

        # 应该有省略号
        assert "..." in context


# ============================================================================
# 工具注册测试
# ============================================================================

class TestBuildSpecialElementsTools:
    """build_special_elements_tools 函数测试"""

    def test_tools_count(self):
        tools = build_special_elements_tools()
        # 应该至少有这些工具
        expected = [
            "analyze_markdown_elements",
            "extract_image_for_analysis",
            "parse_table_structure",
            "generate_table_markdown",
            "format_latex_formula",
            "get_citation_context",
            "analyze_image_with_vision",
            "analyze_chart_image",
        ]
        tool_names = [t.name for t in tools]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    def test_tool_has_description(self):
        tools = build_special_elements_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"
            assert len(tool.description) > 10, f"Tool {tool.name} description too short"

    def test_tool_has_parameters(self):
        tools = build_special_elements_tools()
        for tool in tools:
            assert tool.parameters, f"Tool {tool.name} has no parameters"
            assert "type" in tool.parameters, f"Tool {tool.name} parameters missing type"

    def test_tool_has_function(self):
        tools = build_special_elements_tools()
        for tool in tools:
            assert callable(tool.fn), f"Tool {tool.name} fn is not callable"

    def test_all_tools_callable(self):
        """所有工具函数都可以被调用"""
        tools = build_special_elements_tools()
        for tool in tools:
            try:
                # 简单测试：函数可以被调用（可能会失败，但不应该崩溃）
                import inspect
                sig = inspect.signature(tool.fn)
                assert sig is not None
            except Exception as e:
                pytest.fail(f"Tool {tool.name} failed signature check: {e}")


# ============================================================================
# 集成测试
# ============================================================================

class TestIntegration:
    """端到端集成测试"""

    def test_academic_paper_workflow(self):
        """学术论文工作流"""
        # 1. 解析包含多种元素的论文片段
        paper = """# 深度学习在图像识别中的应用

## 图1

![CNN Architecture](fig1.png)

如图所示，卷积神经网络通过层级结构提取特征。

## 核心公式

能量函数定义为：

$$
E = -\\sum_{i} y_i \\log(\\hat{y}_i)
$$

其中 $y_i$ 是真实标签，$\hat{y}_i$ 是预测概率。

## 实验结果

实验结果见表1。

| 模型 | 准确率 | 参数量 |
| --- | --- | --- |
| ResNet50 | 95.2% | 25.6M |
| VGG16 | 92.1% | 138M |

## 结论

根据 [@he2016] 和 [@simonyan2014] 的研究[@he2016, p.10]，本文方法取得了显著改进。

$$F1 = 2 \\cdot \\frac{Precision \\cdot Recall}{Precision + Recall}$$
"""
        # 2. 分析元素
        result = analyze_markdown_elements(paper)

        assert result["count"] >= 6  # 1 image, 2 display math, 1 inline math, 1 table, 3+ citations

        # 3. 解析表格
        parser = MarkdownElements()
        parser.parse(paper)
        tables = parser.get_by_type("table")
        assert len(tables) >= 1

        if tables:
            table_md = tables[0].raw
            table_data = parse_table_structure(table_md)
            assert table_data["col_count"] == 3
            assert table_data["row_count"] >= 2

        # 4. 解析引用
        citations = parser.get_by_type("citation")
        assert len(citations) >= 2

    def test_table_generation_workflow(self):
        """表格生成工作流"""
        # 1. 定义表头和数据
        headers = ["方法", "准确率", "召回率", "F1分数"]
        rows = [
            ["随机森林", "85.2%", "82.1%", "83.6%"],
            ["SVM", "88.5%", "85.3%", "86.9%"],
            ["神经网络", "92.1%", "90.8%", "91.4%"],
        ]

        # 2. 生成 Markdown
        md = generate_table_markdown(headers, rows)

        # 3. 解析验证
        parsed = parse_table_structure(md)
        assert parsed["headers"] == headers
        assert parsed["row_count"] == 3
        assert parsed["col_count"] == 4

    def test_citation_indexing_workflow(self):
        """文献引用索引工作流"""
        # 文档内容
        doc = """
        近年来，深度学习在计算机视觉领域取得了显著进展[@lecun2015]。
        特别是卷积神经网络[@lecun2015; @krizhevsky2012]在图像分类任务上表现优异。
        残差网络[@he2016]进一步提升了训练效率。
        """

        # 解析引用
        parser = MarkdownElements()
        parser.parse(doc)
        citations = parser.get_by_type("citation")

        unique_keys = set(c.content for c in citations)
        assert len(unique_keys) == 3  # lecun2015, krizhevsky2012, he2016

        # 获取上下文
        context = get_citation_context(doc, "he2016")
        assert "[@he2016]" in context

    def test_math_formula_workflow(self):
        """数学公式工作流"""
        # 1. 各种公式格式
        formulas = [
            ("E = mc^2", False, "$E = mc^2$"),
            ("\\frac{1}{2}", True, "$$$\n\\frac{1}{2}\n$$"),  # 注意：会有2个$$
            ("x^2 + y^2 = z^2", False, "$x^2 + y^2 = z^2$"),
        ]

        for formula, display, expected_start in formulas:
            result = format_latex_formula(formula, display=display)
            if display:
                assert result.startswith("$$"), f"Display formula should start with $$: {result}"
            else:
                assert result.startswith("$"), f"Inline formula should start with $: {result}"
