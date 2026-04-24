"""输出格式化 - 生成双语对照文档"""

from __future__ import annotations

from pathlib import Path

from src.translator.ollama_client import TranslationResult


def format_output(
    results: list[TranslationResult],
    output_format: str = "bilingual",
    file_format: str = "markdown",
) -> str:
    """将翻译结果格式化为输出文档

    Args:
        results: 翻译结果列表
        output_format: bilingual | translated_only | parallel
        file_format: markdown | txt

    Returns:
        格式化后的文本
    """
    if file_format == "markdown":
        return _format_markdown(results, output_format)
    return _format_plain(results, output_format)


def _format_markdown(
    results: list[TranslationResult],
    output_format: str,
) -> str:
    """Markdown 格式输出"""
    lines: list[str] = ["# 翻译结果\n"]

    for i, r in enumerate(results, 1):
        if output_format == "bilingual":
            lines.append(f"## 第 {i} 部分\n")
            lines.append("**原文：**\n")
            lines.append(f"> {r.original}\n")
            lines.append("**译文：**\n")
            lines.append(f"{r.translated}\n")
            lines.append("---\n")
        elif output_format == "parallel":
            lines.append(f"| 原文 | 译文 |\n| --- | --- |\n")
            lines.append(f"| {r.original} | {r.translated} |\n")
        else:  # translated_only
            lines.append(f"{r.translated}\n")

    return "\n".join(lines)


def _format_plain(
    results: list[TranslationResult],
    output_format: str,
) -> str:
    """纯文本格式输出"""
    lines: list[str] = []

    for i, r in enumerate(results, 1):
        if output_format == "bilingual":
            lines.append(f"=== 第 {i} 部分 ===")
            lines.append("[原文]")
            lines.append(r.original)
            lines.append("[译文]")
            lines.append(r.translated)
            lines.append("")
        else:  # translated_only
            lines.append(r.translated)

    return "\n".join(lines)


def save_output(content: str, output_path: str | Path) -> Path:
    """保存输出到文件

    Args:
        content: 格式化后的文本
        output_path: 输出路径

    Returns:
        实际保存路径
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
