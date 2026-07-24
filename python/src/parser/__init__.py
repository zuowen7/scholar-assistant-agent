"""文档解析模块 — 支持 PDF、Word、Excel、PPT、HTML 等 16 种格式"""

from src.parser.article_detector import detect_articles, extract_articles
from src.parser.dispatcher import (
    SUPPORTED_EXTENSIONS,
    extract_document,
    get_supported_extensions,
)
from src.parser.extractor import extract_pages, extract_text

__all__ = [
    "extract_text",
    "extract_pages",
    "extract_document",
    "get_supported_extensions",
    "SUPPORTED_EXTENSIONS",
    "detect_articles",
    "extract_articles",
]
