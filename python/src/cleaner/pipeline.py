"""文本清洗流水线 - 处理 PDF 提取后的格式问题"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CleanResult:
    """清洗结果"""

    text: str
    has_references: bool
    references_start: int  # 引用区在 text 中的起始位置 (-1 表示无)
    references_text: str  # 引用区原文


def clean_text(raw_text: str) -> str:
    """清洗 PDF 提取的原始文本（向后兼容的快捷方法）

    Args:
        raw_text: PDF 提取的原始文本

    Returns:
        清洗后的文本
    """
    return clean_text_full(raw_text).text


def clean_text_full(raw_text: str) -> CleanResult:
    """完整清洗，返回结构化结果

    处理步骤:
    1. 过滤水印文本
    2. 合并被断行打断的单词 (连字符断词)
    3. 合并同段落内的换行
    4. 规范化空白字符
    5. 移除页码标记
    6. 检测引用区
    7. 恢复段落分隔
    """
    text = raw_text

    # 1. 过滤水印
    text = _remove_watermarks(text)

    # 2. 处理连字符断词: "infor-\nmation" → "information"
    text = _fix_hyphenation(text)

    # 3. 合并段落内换行
    text = _merge_paragraph_lines(text)

    # 4. 规范化空白
    text = _normalize_whitespace(text)

    # 5. 移除独立页码行
    text = _remove_page_numbers(text)

    # 6. 压缩连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 7. 检测引用区
    ref_pos, ref_text = _detect_references(text)

    return CleanResult(
        text=text.strip(),
        has_references=ref_pos >= 0,
        references_start=ref_pos,
        references_text=ref_text,
    )


# ---------------------------------------------------------------------------
# 引用区检测
# ---------------------------------------------------------------------------

# 常见引用区标题 (大小写不敏感)
_REFERENCE_PATTERNS = [
    r"REFERENCES\s+AND\s+NOTES",
    r"REFERENCES",
    r"BIBLIOGRAPHY",
    r"LITERATURE\s+CITED",
    r"WORKS\s+CITED",
    r"SUPPLEMENTARY\s+MATERIALS",
    r"ACKNOWLEDGMENTS",
]


def _detect_references(text: str) -> tuple[int, str]:
    """检测引用区起始位置（查找最后一个匹配，避免误截多篇文章）

    Returns:
        (position, reference_text) — position 为 -1 表示未检测到
    """
    best_pos = -1
    for pattern in _REFERENCE_PATTERNS:
        for m in re.finditer(r"^" + pattern, text, re.MULTILINE | re.IGNORECASE):
            if m.start() > best_pos:
                best_pos = m.start()

    if best_pos >= 0:
        refs = text[best_pos:]
        # 如果"引用区"占比过大（>50%），可能是多篇文章误判
        if len(refs) > len(text) * 0.5:
            return -1, ""
        return best_pos, refs
    return -1, ""


# ---------------------------------------------------------------------------
# 水印过滤
# ---------------------------------------------------------------------------

_WATERMARK_PATTERNS = [
    r"^\d+\s+\d+\s+\w+\s+\d{4}\s+Science$",
    r"^\w+\s+\d{4}\s+Science\s+Vol\s+\d+.*$",
    r"^Science\s+\d+.*$",
    r"^PERSPECTIVES$",
    r"^REVIEW$",
    r"^RESEARCH\s+ARTICLE$",
    r"^REPORTS$",
]


def _remove_watermarks(text: str) -> str:
    """移除水印和期刊页眉噪声"""
    # 先处理跨行的 "Downloaded from ... on ..." 水印
    text = re.sub(
        r"Downloaded\s+from\s+.+?\s+on\s+\w+\s+\d+.*?(?=\n|$)",
        "", text, flags=re.DOTALL,
    )
    for pattern in _WATERMARK_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text


# ---------------------------------------------------------------------------
# 原有清洗函数
# ---------------------------------------------------------------------------


def _fix_hyphenation(text: str) -> str:
    """修复连字符断词

    示例: "infor-\\nmation" → "information"
    """
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def _merge_paragraph_lines(text: str) -> str:
    """合并同段落内的换行

    PDF 提取的文本经常在每行末尾产生不必要的换行。
    如果下一行以小写字母开头或不是常见段落起始模式，
    则认为是同一段落的续行。
    """
    lines = text.split("\n")
    merged: list[str] = []
    buffer = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 空行 = 段落分隔
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append("")
            continue

        if not buffer:
            buffer = stripped
        elif _is_continuation(buffer, stripped):
            buffer += " " + stripped
        else:
            merged.append(buffer)
            buffer = stripped

    if buffer:
        merged.append(buffer)

    return "\n".join(merged)


def _is_continuation(prev_line: str, current_line: str) -> bool:
    """判断当前行是否是上一行的续行

    续行特征:
    - 当前行以小写字母开头
    - 上一行以句号、问号、感叹号结尾时，通常不是续行
    """
    # 上一行以句末标点结尾 → 新段落
    if prev_line.rstrip() and prev_line.rstrip()[-1] in ".!?":
        return False

    # 当前行以大写字母开头 + 看起来像标题/列表 → 新段落
    if current_line[0].isupper() and _looks_like_heading(current_line):
        return False

    # 当前行以小写字母开头 → 续行
    if current_line[0].islower():
        return True

    # 默认视为新段落
    return False


def _looks_like_heading(line: str) -> bool:
    """判断是否像标题行"""
    return len(line) < 80 and not line.endswith((".", ",", ";", ":"))


def _normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    text = text.replace("\t", " ")
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"^ +| +$", "", text, flags=re.MULTILINE)
    return text


def _remove_page_numbers(text: str) -> str:
    """移除独立页码行"""
    patterns = [
        r"^\s*\d+\s*$",
        r"^\s*[-–—]\s*\d+\s*[-–—]\s*$",
        r"^\s*[Pp]age\s+\d+\s*$",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text
