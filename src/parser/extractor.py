"""PDF 文本提取器 - 基于 pdfplumber"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class PageContent:
    """单页提取结果"""

    page_num: int
    text: str
    width: float
    height: float


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
    """逐页提取 PDF 文本

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
                text = page.extract_text() or ""
                pages.append(
                    PageContent(
                        page_num=i + 1,
                        text=text,
                        width=page.width,
                        height=page.height,
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
