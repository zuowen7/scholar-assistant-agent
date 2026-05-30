"""输出格式化模块"""

from src.formatter.renderer import format_blocks, format_output
from src.formatter.pptx_exporter import build_paper_pptx, export_translated_paper_to_pptx, HAS_PPTX
from src.formatter.data_availability import (
    generate_statement,
    format_data_availability_section,
    DatasetInfo,
    AccessRoute,
    DataAvailabilityResult,
)


def markdown_to_docx(*args, **kwargs):
    """Lazy Word exporter import.

    Importing the formatter package should not crash translation/parser routes
    when optional Word-export dependencies are missing in a dev environment.
    """
    try:
        from src.formatter.word_exporter import markdown_to_docx as _markdown_to_docx
    except ModuleNotFoundError as e:
        missing = getattr(e, "name", "") or "python-docx/lxml"
        raise RuntimeError(
            f"Word export requires optional dependency '{missing}'. "
            "Install python requirements-lock.txt before exporting .docx files."
        ) from e
    return _markdown_to_docx(*args, **kwargs)

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
