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

    # 6. 移除脚注、致谢、注释等非正文段落
    text = _remove_annotations(text)

    # 7. 压缩连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 8. 检测引用区 → 直接从正文中删除，不翻译、不显示
    ref_pos, ref_text = _detect_references(text)
    if ref_pos >= 0:
        text = text[:ref_pos].rstrip()

    return CleanResult(
        text=text.strip(),
        has_references=ref_pos >= 0,
        references_start=ref_pos,
        references_text=ref_text,
    )


# ---------------------------------------------------------------------------
# 引用区检测
# ---------------------------------------------------------------------------

# 常见引用区标题 — 从共享常量导入，消重复一
from src.constants import REFERENCE_SECTION_PATTERNS as _REFERENCE_PATTERNS

_REFERENCE_PATTERNS = [r"^" + p + r"\s*$" for p in _REFERENCE_PATTERNS]


def _detect_references(text: str) -> tuple[int, str]:
    """检测引用区起始位置（查找最后一个匹配，避免误截多篇文章）

    Returns:
        (position, reference_text) — position 为 -1 表示未检测到
    """
    best_pos = -1
    for pattern in _REFERENCE_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
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


def _remove_annotations(text: str) -> str:
    """移除脚注、致谢、注释、作者贡献等非正文段落"""
    # 脚注标记: 独立一行只有上标数字或 [数字] 或 上标 a/b/c
    text = re.sub(r"^\^?\d{1,3}[a-z]?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\[\d+\]$", "", text, flags=re.MULTILINE)
    # 致谢/注释/作者贡献/利益声明 等段落（整段删除）
    anno_section_headers = [
        r"^Acknowledgments?\s*:?",
        r"^Funding\s*:",
        r"^Author\s+(?:Contributions?|Information)$",
        r"^Competing\s+Interests?:?",
        r"^Data\s+(?:Availability|Access)\s+Statement",
        r"^Ethics\s+(?:Statement|Approval|Declarations?)",
        r"^Consent\s+to\s+(?:Participate|Publish)",
        r"^Conflicts?\s+of\s+Interests?",
        r"^Financial\s+Disclosure",
        r"^Declaration\s+of\s+",
        r"^Supplementary\s+(?:Information|Data|Material|Note)",
        r"^Footnotes?\s*:?",
        r"^Notes?\s*:?",
        r"^Additional\s+(?:Information|File)",
        r"^Electronic\s+Supplementary",
        r"^Supporting\s+Information",
        r"^Author\s+e-mail",
        r"^Correspondence",
        r"^See\s+(?:also\s+)?(?:Appendix|Table|Figure|Fig\.?|Supplementary)",
    ]
    for pattern in anno_section_headers:
        # 匹配该行及后续直到空行的内容
        text = re.sub(
            pattern + r"[^\n]*(?:\n(?!\n)[^\n]*)*",
            "", text, flags=re.MULTILINE | re.IGNORECASE,
        )
    # 删除单独的脚注内容行: "1 Author Name, Title, Journal (2020) pp. 1-10"
    text = re.sub(r"^\d{1,3}\s+[A-Z][a-z]+.+?\(\d{4}\).*$", "", text, flags=re.MULTILINE)
    return text


# ---------------------------------------------------------------------------
# 原有清洗函数
# ---------------------------------------------------------------------------


def _fix_hyphenation(text: str) -> str:
    """修复连字符断词

    示例: "infor-\\nmation" → "information"
    支持 \\r\\n 和连字符后有空格的情况。
    """
    # 匹配 word-后跟可选空格和换行符(\r\n, \r, \n)，再跟word
    return re.sub(r"(\w)-\s*\r?\n\s*(\w)", r"\1\2", text)


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
    - 英文: 当前行以小写字母开头
    - 中文: 上一行未以句末标点结尾时视为续行
    - 上一行以句号、问号、感叹号结尾时，通常不是续行
    - LaTeX 环境（\\begin/\\end）始终视为新段落
    """
    prev_stripped = prev_line.rstrip()

    # LaTeX 环境: \begin{...} 或 \end{...} 或 $$ 始终作为新段落边界
    if prev_stripped and re.match(r"^\\(?:begin|end)\{", prev_stripped):
        return False
    if current_line and re.match(r"^\\(?:begin|end)\{", current_line):
        return False
    if prev_stripped and prev_stripped.strip() in ("$$", r"\[", r"\]"):
        return False
    if current_line and current_line.strip() in ("$$", r"\[", r"\]"):
        return False

    # 上一行以句末标点（含中文标点）结尾 → 新段落
    if prev_stripped and prev_stripped[-1] in ".!?。！？；":
        return False

    # 当前行首字符
    first_char = current_line[0]

    # 中文文本: 非句末标点结尾时视为续行
    if prev_stripped and '\u4e00' <= prev_stripped[-1] <= '\u9fff':
        return True

    # 当前行以大写字母开头 + 看起来像标题/列表 → 新段落
    if first_char.isupper() and _looks_like_heading(current_line):
        return False

    # 当前行以小写字母开头 → 续行
    if first_char.islower():
        return True

    # 中文行首也视为续行（中文没有大小写）
    if '\u4e00' <= first_char <= '\u9fff':
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
