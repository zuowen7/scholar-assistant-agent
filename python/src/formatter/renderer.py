"""输出格式化 - 生成双语对照文档"""

from __future__ import annotations

import re
from pathlib import Path

from src.translator.ollama_client import TranslationResult


def format_output(
    results: list[TranslationResult],
    output_format: str = "bilingual",
    file_format: str = "markdown",
) -> str:
    if file_format == "markdown":
        return _format_markdown(results, output_format)
    return _format_plain(results, output_format)


def _format_markdown(
    results: list[TranslationResult],
    output_format: str,
) -> str:
    if output_format == "bilingual":
        return _format_bilingual_md(results)
    if output_format == "parallel":
        return _format_parallel_md(results)
    return _format_translated_only_md(results)


def _format_bilingual_md(results: list[TranslationResult]) -> str:
    parts: list[str] = []

    for i, r in enumerate(results):
        if i > 0:
            parts.append("")
            parts.append("---")
            parts.append("")

        orig_paragraphs = _split_paragraphs(r.original)
        trans_paragraphs = _split_paragraphs(r.translated)

        parts.append(f"## 第 {i + 1} 部分")
        parts.append("")

        max_paras = max(len(orig_paragraphs), len(trans_paragraphs))
        for j in range(max_paras):
            orig = orig_paragraphs[j] if j < len(orig_paragraphs) else ""
            trans = trans_paragraphs[j] if j < len(trans_paragraphs) else ""

            if orig:
                for line in orig.split("\n"):
                    parts.append(f"> {line}")
                parts.append("")
            if trans:
                parts.append(trans)
                parts.append("")

    return "\n".join(parts)


def _format_parallel_md(results: list[TranslationResult]) -> str:
    lines: list[str] = []
    lines.append("| 原文 | 译文 |")
    lines.append("| --- | --- |")

    for r in results:
        orig_escaped = _md_table_escape(r.original)
        trans_escaped = _md_table_escape(r.translated)
        lines.append(f"| {orig_escaped} | {trans_escaped} |")

    lines.append("")
    return "\n".join(lines)


def _format_translated_only_md(results: list[TranslationResult]) -> str:
    parts: list[str] = []
    for r in results:
        text = r.translated.strip()
        if text:
            parts.append(text)
            parts.append("")
    return "\n".join(parts)


def _format_plain(
    results: list[TranslationResult],
    output_format: str,
) -> str:
    lines: list[str] = []

    if output_format == "bilingual":
        for i, r in enumerate(results):
            if i > 0:
                lines.append("")
            lines.append(f"{'=' * 20} 第 {i + 1} 部分 {'=' * 20}")
            lines.append("")
            lines.append("[原文]")
            lines.append(r.original)
            lines.append("")
            lines.append("[译文]")
            lines.append(r.translated)
            lines.append("")
    else:
        for r in results:
            text = r.translated.strip()
            if text:
                lines.append(text)
                lines.append("")

    return "\n".join(lines)


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n{2,}", text.strip())
    return [p.strip() for p in paras if p.strip()]


def _md_table_escape(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    return text


def save_output(content: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
