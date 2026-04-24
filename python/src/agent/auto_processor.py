"""Agent 自动预处理 — 检测并处理特殊元素

当用户发送包含图片、表格、公式等特殊元素的消息时，
自动调用相应工具分析这些元素，并将结果注入到 Agent 的上下文中。

这让 Agent 能够自主理解用户消息中的特殊元素，
无需用户显式要求"帮我分析这张图片"。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.models import Message

logger = logging.getLogger(__name__)

# 检测模式
# Unix 路径: /path/to/image.png
UNIX_IMAGE_PATTERN = re.compile(
    r"(?:^|[\s(])(/[^\s()]+?\.(?:png|jpg|jpeg|gif|webp|bmp))",
    re.IGNORECASE,
)

# Windows 路径: C:\path\to\image.png 或 C:/path/to/image.png
WINDOWS_IMAGE_PATTERN = re.compile(
    r"([A-Za-z]:[^\s()]+?\.(?:png|jpg|jpeg|gif|webp|bmp))",
    re.IGNORECASE,
)

# Markdown 图片: ![alt](url)
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[(?:[^\]]*)\]\(([^)]+)\)")

TABLE_PATTERN = re.compile(
    r"^\|.+\|\s*$",
    re.MULTILINE,
)

CITATION_PATTERN = re.compile(r"\[@[a-zA-Z0-9_]+\]")


@dataclass
class AutoProcessResult:
    """自动处理结果"""

    # 是否检测到特殊元素
    has_special_elements: bool

    # 检测到的元素摘要
    detected_elements: list[str]

    # 工具调用结果
    tool_results: list[str]

    # 是否需要 Agent 处理
    needs_agent: bool

    # 增强后的用户消息
    enhanced_query: str


class AutoElementProcessor:
    """特殊元素自动处理器"""

    def __init__(self):
        self._element_patterns = {
            "image": {
                "patterns": [MARKDOWN_IMAGE_PATTERN, UNIX_IMAGE_PATTERN, WINDOWS_IMAGE_PATTERN],
                "tool": "analyze_image_with_vision",
                "description": "图片",
            },
            "table": {
                "patterns": [TABLE_PATTERN],
                "tool": "parse_table_structure",
                "description": "表格",
            },
            "citation": {
                "patterns": [CITATION_PATTERN],
                "tool": "get_citation_context",
                "description": "文献引用",
            },
        }

    def detect_elements(self, text: str) -> dict[str, list[str]]:
        """检测文本中的特殊元素

        Returns:
            {element_type: [detected_values]}
        """
        detected: dict[str, list[str]] = {}

        # 检测图片
        image_matches: list[str] = []
        seen_paths: set[str] = set()

        # Markdown 图片语法: ![alt](url)
        for match in MARKDOWN_IMAGE_PATTERN.finditer(text):
            url = match.group(1) if match.lastindex else match.group(0)
            if url and url not in seen_paths:
                image_matches.append(url)
                seen_paths.add(url)

        # Unix 文件路径
        for match in UNIX_IMAGE_PATTERN.finditer(text):
            path = match.group(1) if match.lastindex else match.group(0)
            if path and path not in seen_paths:
                image_matches.append(path)
                seen_paths.add(path)

        # Windows 文件路径
        for match in WINDOWS_IMAGE_PATTERN.finditer(text):
            path = match.group(1) if match.lastindex else match.group(0)
            if path and path not in seen_paths:
                image_matches.append(path)
                seen_paths.add(path)

        if image_matches:
            detected["image"] = image_matches

        # 检测表格（简化：检测包含 | 的行）
        table_lines = [line.strip() for line in text.split("\n") if "|" in line and line.strip().startswith("|")]
        if len(table_lines) >= 2:  # 至少表头和一行数据
            detected["table"] = table_lines

        # 检测引用
        citation_matches = list(set(CITATION_PATTERN.findall(text)))
        if citation_matches:
            detected["citation"] = citation_matches

        return detected

    async def process_async(
        self,
        query: str,
        context_text: str | None = None,
    ) -> AutoProcessResult:
        """异步处理特殊元素

        Args:
            query: 用户原始消息
            context_text: 可选的上下文文本

        Returns:
            AutoProcessResult，包含检测结果和处理结果
        """
        combined_text = f"{query}\n{context_text or ''}"
        detected = self.detect_elements(combined_text)

        if not detected:
            return AutoProcessResult(
                has_special_elements=False,
                detected_elements=[],
                tool_results=[],
                needs_agent=False,
                enhanced_query=query,
            )

        tool_results: list[str] = []
        detected_summaries: list[str] = []
        analysis_contexts: list[str] = []

        # 处理图片
        if "image" in detected:
            for img_path in detected["image"]:
                img_path = img_path.strip()
                if img_path and not img_path.startswith("http"):
                    try:
                        result = await self._analyze_image(img_path)
                        tool_results.append(f"[图片分析: {img_path}]\n{result}")
                        analysis_contexts.append(result)
                        detected_summaries.append(f"1张图片 ({img_path})")
                    except Exception as e:
                        logger.warning("图片分析失败: %s - %s", img_path, e)
                        tool_results.append(f"[图片分析: {img_path}]\n分析失败: {e}")

        # 处理表格
        if "table" in detected:
            table_text = "\n".join(detected["table"])
            try:
                result = await self._parse_table(table_text)
                tool_results.append(f"[表格结构]\n{result}")
                analysis_contexts.append(result)
                detected_summaries.append(f"1个表格")
            except Exception as e:
                logger.warning("表格解析失败: %s", e)

        # 处理引用
        if "citation" in detected:
            citations = detected["citation"]
            try:
                for citation in citations:
                    result = await self._get_citation_context(combined_text, citation)
                    tool_results.append(f"[引用 {citation}]\n{result}")
                    analysis_contexts.append(result)
                detected_summaries.append(f"{len(citations)}个引用")
            except Exception as e:
                logger.warning("引用上下文获取失败: %s", e)

        # 构建增强后的查询
        enhanced_parts = [query]

        if analysis_contexts:
            enhanced_parts.append("\n\n--- 特殊元素自动分析结果 ---\n")
            enhanced_parts.append("\n\n".join(analysis_contexts))
            enhanced_parts.append("\n--- 分析结果结束 ---\n")

        enhanced_parts.append("\n\n请基于以上分析结果回答用户的问题。")

        enhanced_query = "".join(enhanced_parts)

        return AutoProcessResult(
            has_special_elements=True,
            detected_elements=detected_summaries,
            tool_results=tool_results,
            needs_agent=True,
            enhanced_query=enhanced_query,
        )

    async def _analyze_image(self, image_path: str) -> str:
        """异步分析图片"""
        from src.agent.special_elements import analyze_image_with_vision
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, analyze_image_with_vision, image_path)
        return result

    async def _parse_table(self, table_text: str) -> str:
        """异步解析表格"""
        from src.agent.special_elements import parse_table_structure
        import json
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, parse_table_structure, table_text)
        return json.dumps(result, ensure_ascii=False, indent=2)

    async def _get_citation_context(self, text: str, citation_key: str) -> str:
        """异步获取引用上下文"""
        from src.agent.special_elements import get_citation_context
        # 提取 key（去掉 [@ 和 ]）
        key = citation_key.replace("[@", "").replace("]", "").strip()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_citation_context, text, key)
        return result


async def auto_process_message(
    query: str,
    context_text: str | None = None,
) -> AutoProcessResult:
    """快捷函数：自动处理用户消息中的特殊元素

    Args:
        query: 用户原始消息
        context_text: 可选的上下文文本

    Returns:
        AutoProcessResult
    """
    processor = AutoElementProcessor()
    return await processor.process_async(query, context_text)


def enrich_system_prompt(base_prompt: str) -> str:
    """增强系统提示词，让 Agent 知道如何处理特殊元素

    Returns:
        增强后的系统提示词
    """
    enhancement = """

## 特殊元素处理能力

当你收到用户消息时，请自动检测并处理以下特殊元素：

### 1. 图片
- 如果用户消息包含图片路径（如 `/path/to/image.png`）或 Markdown 图片语法（`![alt](url)`）
- 自动调用 `analyze_image_with_vision` 或 `analyze_chart_image` 工具分析图片
- 根据分析结果回答用户关于图片的问题

### 2. 表格
- 如果用户消息包含 Markdown 表格（以 `|` 开头）
- 自动调用 `parse_table_structure` 工具解析表格结构
- 可以调用 `generate_table_markdown` 生成或修改表格

### 3. 文献引用
- 如果用户消息包含引用标记（如 `[@smith2020]`）
- 自动调用 `get_citation_context` 获取引用上下文
- 帮助用户理解引用的用途

### 4. 数学公式
- 如果用户消息包含 LaTeX 公式（`$...$` 或 `$$...$$`）
- 使用你的数学知识理解和解释公式
- 可调用 `format_latex_formula` 格式化公式

## 处理流程
1. 检测消息中的特殊元素
2. 自动调用相应工具（如有必要）
3. 基于工具返回结果和你的理解回答用户

请始终主动检测和处理特殊元素，无需用户明确要求"帮我分析图片"等。
"""
    return base_prompt + enhancement
