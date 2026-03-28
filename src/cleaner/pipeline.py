"""文本清洗流水线 - 处理 PDF 提取后的格式问题"""

from __future__ import annotations

import re


def clean_text(raw_text: str) -> str:
    """清洗 PDF 提取的原始文本

    处理步骤:
    1. 合并被断行打断的单词 (连字符断词)
    2. 合并同段落内的换行
    3. 规范化空白字符
    4. 移除页码标记
    5. 恢复段落分隔

    Args:
        raw_text: PDF 提取的原始文本

    Returns:
        清洗后的文本
    """
    text = raw_text

    # 1. 处理连字符断词: "infor-\nmation" → "information"
    text = _fix_hyphenation(text)

    # 2. 合并段落内换行: 非空行后紧跟非空行（无空行间隔）视为同段落
    text = _merge_paragraph_lines(text)

    # 3. 规范化空白
    text = _normalize_whitespace(text)

    # 4. 移除独立页码行 (如 "12", "- 12 -", "Page 12")
    text = _remove_page_numbers(text)

    # 5. 压缩连续空行为最多两个换行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


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
    - 当前行以逗号、分号等标点开头的情况较少见，但也可能是续行
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
    # 短行 + 首字母大写 = 可能是标题
    return len(line) < 80 and not line.endswith((".", ",", ";", ":"))


def _normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    # 制表符替换为空格
    text = text.replace("\t", " ")
    # 多个连续空格压缩为一个
    text = re.sub(r" {2,}", " ", text)
    # 行首行尾空格
    text = re.sub(r"^ +| +$", "", text, flags=re.MULTILINE)
    return text


def _remove_page_numbers(text: str) -> str:
    """移除独立页码行"""
    # 匹配: "12", "- 12 -", "Page 12", "第 12 页" 等
    patterns = [
        r"^\s*\d+\s*$",                           # 纯数字
        r"^\s*[-–—]\s*\d+\s*[-–—]\s*$",           # - 12 -
        r"^\s*[Pp]age\s+\d+\s*$",                  # Page 12
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text
