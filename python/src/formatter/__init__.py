"""输出格式化模块"""

from src.formatter.renderer import format_blocks, format_output
from src.formatter.word_exporter import markdown_to_docx
from src.formatter.pptx_exporter import build_paper_pptx, export_translated_paper_to_pptx, HAS_PPTX
from src.formatter.data_availability import (
    generate_statement,
    format_data_availability_section,
    DatasetInfo,
    AccessRoute,
    DataAvailabilityResult,
)

__all__ = [
    "format_blocks",
    "format_output",
    "markdown_to_docx",
    "build_paper_pptx",
    "export_translated_paper_to_pptx",
    "HAS_PPTX",
    "generate_statement",
    "format_data_availability_section",
    "DatasetInfo",
    "AccessRoute",
    "DataAvailabilityResult",
]
