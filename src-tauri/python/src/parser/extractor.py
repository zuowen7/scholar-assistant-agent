"""PDF 文本提取器 - 基于 pdfplumber，支持双栏布局检测"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


@dataclass
class PageContent:
    """单页提取结果"""

    page_num: int
    text: str
    width: float
    height: float
    is_dual_column: bool = False


@dataclass
class DocumentContent:
    """整篇文档提取结果"""

    pages: list[PageContent]
    source_path: str

    @property
    def full_text(self) -> str:
        """拼接所有页面文本"""
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def page_count(self) -> int:
        return len(self.pages)


def extract_pages(pdf_path: str | Path) -> DocumentContent:
    """逐页提取 PDF 文本，自动检测双栏布局

    Args:
        pdf_path: PDF 文件路径

    Returns:
        DocumentContent 包含所有页面的提取结果

    Raises:
        FileNotFoundError: PDF 文件不存在
        ValueError: PDF 无法解析
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    pages: list[PageContent] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                is_dual = _detect_columns(page)
                if is_dual:
                    text = _extract_dual_column(page)
                    # 双栏提取也可能存在词间距丢失，回退到字符级提取
                    if _has_missing_spaces(text):
                        char_text = _extract_with_char_spaces(page)
                        if char_text and len(char_text) > len(text) * 0.6:
                            text = char_text
                else:
                    text = page.extract_text() or ""
                    text = _filter_header_footer(text, page)

                    # 检测词间距丢失: 如果提取文本中几乎没有空格，说明 PDF 编码缺少空格字符
                    # 此时回退到基于字符坐标的空格推断
                    if _has_missing_spaces(text):
                        char_text = _extract_with_char_spaces(page)
                        if char_text and len(char_text) > len(text) * 0.8:
                            text = char_text

                pages.append(
                    PageContent(
                        page_num=i + 1,
                        text=text,
                        width=page.width,
                        height=page.height,
                        is_dual_column=is_dual,
                    )
                )
    except Exception as e:
        raise ValueError(f"PDF 解析失败: {pdf_path} - {e}") from e

    return DocumentContent(pages=pages, source_path=str(pdf_path))


def extract_text(pdf_path: str | Path) -> str:
    """提取 PDF 全文文本（快捷方法）

    Args:
        pdf_path: PDF 文件路径

    Returns:
        拼接后的全文文本
    """
    doc = extract_pages(pdf_path)
    return doc.full_text


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------

def _detect_columns(page: pdfplumber.page.Page) -> bool:
    """检测页面是否为双栏布局

    逻辑:
    1. 取页面所有 word 的 x0 坐标
    2. 以 page.width/2 为界，统计左右两侧 word 数量
    3. 若左右两侧都有大量文字 (各 > 50 words) 且中间有明显空隙 → 双栏
    """
    words = page.extract_words()
    if len(words) < 100:
        return False

    midpoint = page.width / 2
    margin = page.width * 0.05  # 中间区域容差

    left_count = 0
    right_count = 0
    center_count = 0

    for w in words:
        x_center = (w["x0"] + w["x1"]) / 2
        if x_center < midpoint - margin:
            left_count += 1
        elif x_center > midpoint + margin:
            right_count += 1
        else:
            center_count += 1

    # 左右两侧都有充足文字，且中间区域相对稀疏
    if left_count > 50 and right_count > 50:
        # 中间区域密度应低于两侧
        total = left_count + right_count + center_count
        center_ratio = center_count / total if total > 0 else 1
        return center_ratio < 0.15

    return False


def _extract_dual_column(page: pdfplumber.page.Page) -> str:
    """双栏页面: 基于词坐标+字体信息提取文本，过滤图片标注

    策略:
    1. 提取带字体信息的 word 列表
    2. 检测正文主字体（出现频率最高的字体）
    3. 过滤非主字体词（图片标注、水印等）
    4. 按 y 坐标分行，检测 x 间距拆分交错文本
    """
    midpoint = page.width / 2
    header_cutoff = page.height * 0.05
    footer_cutoff = page.height * 0.95

    words = page.extract_words(extra_attrs=["fontname", "size"])
    if not words:
        return ""

    # 过滤页眉页脚范围外的词
    body_words = [
        w for w in words
        if header_cutoff <= w["top"] <= footer_cutoff
    ]

    # 过滤竖排标注: x0 过小 或 字号过小
    min_x = page.width * 0.04
    body_words = [
        w for w in body_words
        if w["x0"] >= min_x and w.get("size", 99) >= 6.0
    ]

    # 检测正文主字体
    body_font = _detect_body_font(body_words, midpoint)

    # 过滤非正文字体词（图片标注、水印等）
    if body_font:
        filtered = [w for w in body_words if _is_same_font_family(w.get("fontname", ""), body_font)]
    else:
        filtered = body_words

    # 按左右栏分组
    left_words = [w for w in filtered if (w["x0"] + w["x1"]) / 2 < midpoint]
    right_words = [w for w in filtered if (w["x0"] + w["x1"]) / 2 >= midpoint]

    left_text = _words_to_text(left_words)
    right_text = _words_to_text(right_words)

    parts = []
    if left_text.strip():
        parts.append(left_text.strip())
    if right_text.strip():
        parts.append(right_text.strip())

    return "\n\n".join(parts)


def _detect_body_font(words: list[dict], midpoint: float) -> str:
    """检测正文主字体（按词数量统计出现最多的字体名）

    只统计左栏前 1/3 区域的词，避免图片标注干扰。
    """
    from collections import Counter

    # 只看左栏前 1/3 区域的词（最可能是纯正文区域）
    y_max = max(w["top"] for w in words) if words else 0
    region_words = [
        w for w in words
        if w["x0"] < midpoint and w["top"] < y_max * 0.4
    ]
    if not region_words:
        region_words = [w for w in words if w["x0"] < midpoint][:50]

    if not region_words:
        return ""

    font_counts = Counter(w.get("fontname", "") for w in region_words)
    return font_counts.most_common(1)[0][0] if font_counts else ""


def _is_same_font_family(fontname: str, body_font: str) -> bool:
    """判断字体是否属于正文字体家族

    策略: 比较字体名的前缀（去掉 foundry tag 如 NXJRQW+）
    """
    def _normalize(name: str) -> str:
        # 去掉 PDF 子集化前缀 (如 "NXJRQW+ BentonSansCon" → "BentonSansCon")
        if "+" in name:
            name = name.split("+", 1)[1]
        return name.split("-")[0].lower()  # BentonSans, MillerDaily 等

    return _normalize(fontname) == _normalize(body_font)


def _words_to_text(words: list[dict]) -> str:
    """将 word 列表还原为文本行

    按 y 坐标分行 (容差 3pt)，同行内按 x 坐标排序。
    """
    if not words:
        return ""

    words.sort(key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    current_line: list[dict] = [words[0]]

    for w in words[1:]:
        if abs(w["top"] - current_line[0]["top"]) <= 3:
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
    if current_line:
        lines.append(current_line)

    text_lines = []
    for line_words in lines:
        line_words.sort(key=lambda w: w["x0"])
        text_lines.append(" ".join(w["text"] for w in line_words))

    return "\n".join(text_lines)


def _filter_header_footer(text: str, page: pdfplumber.page.Page) -> str:
    """过滤页眉页脚噪声

    通过分析文字 y 坐标分布，去除页面顶部 header_cutoff 以上
    和底部 footer_cutoff 以下的行。
    """
    words = page.extract_words()
    if not words:
        return text

    header_cutoff = page.height * 0.05
    footer_cutoff = page.height * 0.95

    # extract_words() 返回的 top/bottom 都是从页面顶部算起的，直接使用即可
    body_words = [
        w for w in words
        if w.get("top", 0) >= header_cutoff
        and w.get("top", 0) <= footer_cutoff
    ]

    if not body_words:
        return text

    # 如果所有词都在正文中，直接返回
    if len(body_words) == len(words):
        return text

    # 重新从 body 区域提取文本
    body_top = min(w["top"] for w in body_words)
    body_bottom = max(w["bottom"] for w in body_words)

    # pdfplumber crop 的 y 坐标: y0=顶部距离, 但内部是 bottom 坐标系
    # 使用 (x0, top_0, x1, bottom_1) 格式
    cropped = page.crop((0, body_top - 2, page.width, body_bottom + 2))
    return cropped.extract_text() or text


def _has_missing_spaces(text: str) -> bool:
    """检测提取文本是否存在词间距丢失

    判断标准: 文本中连续字母序列（无空格）的平均长度异常长
    """
    if not text or len(text) < 200:
        return False

    # 统计连续字母段的长度
    import re
    alpha_runs = re.findall(r"[a-zA-Z]{10,}", text)
    if not alpha_runs:
        return False

    # 如果有很多长连续字母段（>30字符），说明空格缺失
    long_runs = [r for r in alpha_runs if len(r) > 30]
    if len(long_runs) > 5:
        return True

    # 或者平均连续字母段长度异常
    avg_len = sum(len(r) for r in alpha_runs) / max(len(alpha_runs), 1)
    if avg_len > 50:
        return True

    return False


def _extract_with_char_spaces(page: pdfplumber.page.Page) -> str:
    """基于字符坐标推断空格位置，用于处理 PDF 词间距丢失问题

    策略:
    1. 提取所有字符及其 x/y 坐标
    2. 按 y 坐标分行（同一线上的字符视为同一行）
    3. 行内按 x 排序，根据相邻字符间距推断是否插入空格
    4. 空格阈值与字号成正比
    """
    chars = page.chars
    if not chars:
        return ""

    header_cutoff = page.height * 0.05
    footer_cutoff = page.height * 0.95

    # 过滤页眉页脚字符
    body_chars = [
        c for c in chars
        if header_cutoff <= c.get("top", 0) <= footer_cutoff
    ]
    if not body_chars:
        return ""

    # 按 y 坐标分行 (容差 3pt)
    body_chars.sort(key=lambda c: (c["top"], c["x0"]))
    lines: list[list[dict]] = []
    current_line: list[dict] = [body_chars[0]]

    for c in body_chars[1:]:
        if abs(c["top"] - current_line[0]["top"]) <= 3:
            current_line.append(c)
        else:
            lines.append(current_line)
            current_line = [c]
    if current_line:
        lines.append(current_line)

    text_lines: list[str] = []
    for line_chars in lines:
        line_chars.sort(key=lambda c: c["x0"])

        # 计算该行的字号（取中位数）
        sizes = [c.get("size", 8) for c in line_chars]
        sizes.sort()
        median_size = sizes[len(sizes) // 2] if sizes else 8

        # 空格阈值: 字号的 20%~30%
        # 通过分析行内所有相邻字符间距来自适应
        gaps = []
        for j in range(1, len(line_chars)):
            gap = line_chars[j]["x0"] - line_chars[j - 1]["x1"]
            if gap > 0:
                gaps.append(gap)

        if gaps:
            # 词内间隙通常 < 0.3pt，词间间隙通常 > 0.8pt
            # 使用固定阈值 0.5pt，这对所有字号都安全
            space_threshold = 0.5
        else:
            space_threshold = 0.5

        # 重建行文本
        parts: list[str] = []
        for j, c in enumerate(line_chars):
            if j > 0:
                gap = c["x0"] - line_chars[j - 1]["x1"]
                if gap > space_threshold:
                    parts.append(" ")
            parts.append(c["text"])

        text_lines.append("".join(parts))

    return "\n".join(text_lines)
