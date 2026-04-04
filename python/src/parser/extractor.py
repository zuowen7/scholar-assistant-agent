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
                else:
                    text = page.extract_text() or ""
                    text = _filter_header_footer(text, page)

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
    """双栏页面: 分别裁剪左右栏提取文本，拼接返回"""
    midpoint = page.width / 2
    header_cutoff = page.height * 0.05
    footer_cutoff = page.height * 0.95

    # 左栏
    left_bbox = (0, header_cutoff, midpoint - 1, footer_cutoff)
    left_crop = page.crop(left_bbox)
    left_text = left_crop.extract_text() or ""

    # 右栏
    right_bbox = (midpoint + 1, header_cutoff, page.width, footer_cutoff)
    right_crop = page.crop(right_bbox)
    right_text = right_crop.extract_text() or ""

    parts = []
    if left_text.strip():
        parts.append(left_text.strip())
    if right_text.strip():
        parts.append(right_text.strip())

    return "\n\n".join(parts)


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

    # pdfplumber 的 y0 是从底部算起的，需要转换
    # extract_words() 返回的 top 是从页面顶部算起的
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
