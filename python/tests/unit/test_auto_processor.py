"""自动处理器单元测试"""

import pytest
import asyncio
from src.agent.auto_processor import (
    AutoElementProcessor,
    auto_process_message,
    enrich_system_prompt,
)


class TestAutoElementDetector:
    """元素检测测试"""

    def test_detect_no_elements(self):
        processor = AutoElementProcessor()
        text = "这是一段普通的中文文本，没有任何特殊元素。"
        detected = processor.detect_elements(text)
        assert detected == {}

    def test_detect_markdown_image(self):
        processor = AutoElementProcessor()
        text = "这是一张图片: ![Figure 1](path/to/figure.png)"
        detected = processor.detect_elements(text)
        assert "image" in detected
        assert "figure.png" in detected["image"][0]

    def test_detect_local_image_path(self):
        processor = AutoElementProcessor()
        text = "请分析这张图 /data/images/photo.jpg"
        detected = processor.detect_elements(text)
        assert "image" in detected
        assert any("photo.jpg" in p for p in detected["image"])

    def test_detect_windows_image_path(self):
        processor = AutoElementProcessor()
        # Windows 路径需要 / 或空格前缀才能被检测
        text = " (C:\\Users\\Photos\\image.png)"
        detected = processor.detect_elements(text)
        assert "image" in detected

    def test_detect_table(self):
        processor = AutoElementProcessor()
        text = """| 列1 | 列2 |
| --- | --- |
| A | B |"""
        detected = processor.detect_elements(text)
        assert "table" in detected
        assert len(detected["table"]) >= 2

    def test_detect_citation(self):
        processor = AutoElementProcessor()
        text = "根据 [@smith2020] 的研究[@jones2021, p.123]"
        detected = processor.detect_elements(text)
        assert "citation" in detected

    def test_detect_multiple_images(self):
        processor = AutoElementProcessor()
        text = "![img1](a.png) 和 ![img2](b.png)"
        detected = processor.detect_elements(text)
        assert "image" in detected
        assert len(detected["image"]) >= 2

    def test_detect_mixed_elements(self):
        processor = AutoElementProcessor()
        text = """# 标题
![图片](fig.png)
表格：
| A | B |
| --- | --- |
| 1 | 2 |
根据 [@ref1] 的研究。"""
        detected = processor.detect_elements(text)
        assert "image" in detected
        assert "table" in detected
        assert "citation" in detected


class TestAutoElementProcessor:
    """自动处理器测试"""

    def test_process_no_elements(self):
        processor = AutoElementProcessor()
        result = processor.detect_elements("普通文本")

        assert result == {}

    def test_process_with_image_path(self):
        processor = AutoElementProcessor()
        text = "/path/to/image.png"
        result = processor.detect_elements(text)

        assert "image" in result


class TestAutoProcessMessage:
    """auto_process_message 函数测试"""

    def test_async_process_plain_text(self):
        """普通文本不触发特殊元素处理"""
        result = asyncio.run(auto_process_message("你好"))

        assert result.has_special_elements is False
        assert result.detected_elements == []
        assert result.enhanced_query == "你好"  # 查询保持不变

    def test_async_process_with_image(self):
        """包含图片路径的消息"""
        # 注意：这个测试不会真正调用 Vision API（因为路径不存在）
        result = asyncio.run(auto_process_message(
            "请分析这张图 /data/image.png",
            context_text=None
        ))

        # 应该检测到图片
        assert result.has_special_elements is True
        assert any("图片" in e for e in result.detected_elements)

    def test_async_process_with_citation(self):
        """包含引用标记的消息"""
        result = asyncio.run(auto_process_message(
            "[@smith2020] 这篇论文的主要贡献是什么？",
        ))

        assert result.has_special_elements is True
        assert any("引用" in e for e in result.detected_elements)


class TestEnrichSystemPrompt:
    """系统提示词增强测试"""

    def test_enrich_adds_capabilities(self):
        """增强后的提示词应包含特殊元素处理说明"""
        base = "你是一个有用的助手。"
        enhanced = enrich_system_prompt(base)

        assert "特殊元素处理能力" in enhanced
        assert "图片" in enhanced
        assert "analyze_image_with_vision" in enhanced

    def test_enrich_preserves_base(self):
        """增强后的提示词应保留原始内容"""
        base = "原始系统提示词内容"
        enhanced = enrich_system_prompt(base)

        assert "原始系统提示词内容" in enhanced
