"""Bilingual PDF overlay — renders translations on top of/alongside original PDF text."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import fitz

from src.parser.extractor import TextBlock

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).parent.parent.parent / "assets" / "fonts"


def _resolve_font_path(font_path: str | Path | None = None) -> str | None:
    """Return the path to the CJK font file, or None to use Helvetica."""
    if font_path:
        p = Path(font_path)
        if p.exists():
            return str(p)

    bundled = FONT_DIR / "NotoSansSC-Regular.ttf"
    if bundled.exists():
        return str(bundled)

    legacy = FONT_DIR / "NotoSansCJK-Regular.otf"
    if legacy.exists():
        return str(legacy)

    logger.warning("CJK font not found, falling back to Helvetica")
    return None


def overlay_translation(
    src_pdf: str | Path,
    blocks: list[TextBlock],
    translations: dict[str, str],
    output: str | Path,
    mode: Literal["below", "above", "replace"] = "below",
    font_path: str | Path | None = None,
    translation_font_size: float = 9.0,
) -> Path:
    """Overlay bilingual translations onto a PDF.

    Args:
        src_pdf: Path to the original PDF.
        blocks: TextBlock list from extract_document_with_layout().
        translations: Mapping from block_id → translated text.
        output: Destination path for the output PDF.
        mode:
            ``below``  — insert translation below each original line.
            ``above``  — insert translation above each original line, with white background.
            ``replace`` — redact original text and write translation in-place.
        font_path: Path to a CJK .ttf/.otf font (default: bundled NotoSansSC-Regular.ttf).
        translation_font_size: Base font size for translation text in points.

    Returns:
        Path to the generated output PDF.
    """
    src_pdf = Path(src_pdf)
    output = Path(output)

    if not src_pdf.exists():
        raise FileNotFoundError(f"Source PDF not found: {src_pdf}")

    resolved_font_path = _resolve_font_path(font_path)

    try:
        with fitz.open(src_pdf) as doc:
            blocks_by_page: dict[int, list[TextBlock]] = {}
            for block in blocks:
                blocks_by_page.setdefault(block.page, []).append(block)

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_blocks = blocks_by_page.get(page_num, [])

                for block in page_blocks:
                    trans = translations.get(block.block_id)
                    if not trans or not trans.strip():
                        continue

                    if mode == "replace":
                        _overlay_replace(page, block, trans, resolved_font_path, translation_font_size)
                    elif mode == "above":
                        _overlay_above(page, block, trans, resolved_font_path, translation_font_size)
                    else:
                        _overlay_below(page, block, trans, resolved_font_path, translation_font_size)

            doc.save(str(output), garbage=4, deflate=True)
    except Exception as e:
        raise RuntimeError(f"PDF overlay failed: {e}") from e

    return output


def _overlay_below(
    page: fitz.Page,
    block: TextBlock,
    translated: str,
    font_path: str | None,
    base_size: float,
) -> None:
    """Insert translation text below the original block bbox."""
    x0, y0, x1, y1 = block.bbox
    available_width = x1 - x0
    if available_width <= 0:
        return

    font_size = _fit_font_size(translated, available_width, base_size)
    line_height = font_size * 1.4
    start_y = y1 + font_size * 0.3

    if start_y + line_height > page.rect.height - 10:
        _overlay_above(page, block, translated, font_path, base_size * 0.85)
        return

    rect = fitz.Rect(x0, start_y, x1, start_y + line_height * 3)
    insert_kw: dict = dict(color=(0.2, 0.2, 0.5), align=fitz.TEXT_ALIGN_LEFT)
    if font_path:
        insert_kw["fontfile"] = font_path
    else:
        insert_kw["fontname"] = "Helvetica"
    rc = page.insert_textbox(rect, translated, fontsize=font_size, **insert_kw)
    if rc < 0:
        small_size = max(6.0, font_size * 0.8)
        rect2 = fitz.Rect(x0, start_y, x1, start_y + line_height * 4)
        page.insert_textbox(rect2, translated, fontsize=small_size, **insert_kw)


def _overlay_above(
    page: fitz.Page,
    block: TextBlock,
    translated: str,
    font_path: str | None,
    base_size: float,
) -> None:
    """Insert translation above the original block, with white background rectangle."""
    x0, y0, x1, y1 = block.bbox
    available_width = x1 - x0
    if available_width <= 0:
        return

    font_size = _fit_font_size(translated, available_width, base_size)
    line_height = font_size * 1.4

    bg_top = max(10, y0 - line_height * 2.5)
    bg_rect = fitz.Rect(x0, bg_top, x1, y0)
    page.draw_rect(bg_rect, color=None, fill=(1, 1, 1), fill_opacity=0.95)

    insert_kw: dict = dict(fontsize=font_size, color=(0.2, 0.2, 0.5),
                           align=fitz.TEXT_ALIGN_LEFT)
    if font_path:
        insert_kw["fontfile"] = font_path
    else:
        insert_kw["fontname"] = "Helvetica"
    page.insert_textbox(bg_rect, translated, **insert_kw)


def _overlay_replace(
    page: fitz.Page,
    block: TextBlock,
    translated: str,
    font_path: str | None,
    base_size: float,
) -> None:
    """Redact original text and write translation in-place."""
    x0, y0, x1, y1 = block.bbox
    available_width = x1 - x0
    if available_width <= 0:
        return

    font_size = _fit_font_size(translated, available_width, base_size * 0.9)

    redact_rect = fitz.Rect(x0, y0, x1, y1)
    page.add_redact_annot(redact_rect, fill=(1, 1, 1))
    page.apply_redactions()

    text_rect = fitz.Rect(x0, y0, x1, y0 + (y1 - y0) * 1.5)
    insert_kw: dict = dict(fontsize=font_size, color=(0.1, 0.1, 0.4),
                           align=fitz.TEXT_ALIGN_LEFT)
    if font_path:
        insert_kw["fontfile"] = font_path
    else:
        insert_kw["fontname"] = "Helvetica"
    page.insert_textbox(text_rect, translated, **insert_kw)


def _fit_font_size(text: str, available_width: float, base_size: float) -> float:
    """Largest font size (pts) that fits `text` within `available_width`."""
    if available_width <= 0 or not text:
        return base_size

    def avg_char_width(fs: float) -> float:
        cjk = sum(1 for c in text if "一" <= c <= "鿿")
        return fs * 1.1 if cjk / max(len(text), 1) > 0.3 else fs * 0.55

    lo, hi = 4.0, base_size * 1.5
    for _ in range(10):
        mid = (lo + hi) / 2
        if avg_char_width(mid) * len(text) <= available_width:
            lo = mid
        else:
            hi = mid

    return round(lo, 1)