"""PDF 解析模块"""

from src.parser.extractor import extract_text, extract_pages, DocumentContent

# 支持的文件格式
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "PDF",
}

# extract_document 与 extract_pages 同义（DocumentContent 已有 full_text/page_count 属性）
extract_document = extract_pages

__all__ = ["extract_text", "extract_pages", "extract_document", "SUPPORTED_EXTENSIONS"]
