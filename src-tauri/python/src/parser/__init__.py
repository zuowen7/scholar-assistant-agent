"""文档解析模块 — 支持 PDF、Word、Excel、PPT、HTML 等 16 种格式"""

from src.parser.extractor import extract_text, extract_pages
from src.parser.dispatcher import (
    extract_document,
    get_supported_extensions,
    SUPPORTED_EXTENSIONS,
)

__all__ = [
    "extract_text",
    "extract_pages",
    "extract_document",
    "get_supported_extensions",
    "SUPPORTED_EXTENSIONS",
]
