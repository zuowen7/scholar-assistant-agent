"""Bilingual PDF overlay — renders translations alongside original PDF text."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import fitz

from src.parser.extractor import TextBlock

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).parent.parent.parent / "assets" / "fonts"

# Layout constants (PDF points)
PAD_BELOW_ORIGINAL = 2.0   # gap between original text bottom and translation
PAD_ABOVE_NEXT = 1.5       # gap between translation bottom and next block top
MIN_FONT_SIZE = 5.0
LINE_HEIGHT_RATIO = 1.4
BG_COLOR = (0.94, 0.95, 0.99)
TEXT_COLOR = (0.15, 0.15, 0.5)
SEPARATOR_COLOR = (0.55, 0.55, 0.78)


def _resolve_font_path(font_path: str | Path | None = None) -> str | None:
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
    logger.warning("CJK font not found, falling back to built-in china-s")
    return None


def _font_kwargs(font_path: str | None) -> dict:
    if font_path:
        return {"fontfile": font_path, "fontname": "cjk-overlay"}
    return {"fontname": "china-s"}


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF    # CJK Unified Ideographs
        or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
        or 0x3000 <= cp <= 0x303F  # CJK Symbols
        or 0xFF00 <= cp <= 0xFFEF  # Fullwidth Forms
        or 0x2E80 <= cp <= 0x2FDF  # CJK Radicals
        or 0xF900 <= cp <= 0xFAFF  # CJK Compatibility Ideographs
    )


def _estimate_lines(text: str, avail_w: float, font_size: float) -> int:
    """Simulate line wrapping with per-character width for accurate line count."""
    if not text or avail_w <= 0:
        return 1
    current_w = 0.0
    lines = 1
    for ch in text:
        cw = font_size * (1.05 if _is_cjk(ch) else 0.55)
        current_w += cw
        if current_w > avail_w:
            lines += 1
            current_w = cw
    return lines


def _fit_font_size(
    text: str,
    avail_w: float,
    avail_h: float,
    base_size: float,
) -> float:
    """Largest font size that fits `text` within avail_w × avail_h."""
    if not text or avail_w <= 0 or avail_h <= 0:
        return max(MIN_FONT_SIZE, min(base_size, avail_h / LINE_HEIGHT_RATIO))

    max_fs = min(base_size * 1.5, avail_h / LINE_HEIGHT_RATIO)
    if max_fs < MIN_FONT_SIZE:
        return MIN_FONT_SIZE

    lo, hi = MIN_FONT_SIZE, max_fs
    for _ in range(15):
        mid = (lo + hi) / 2
        n_lines = _estimate_lines(text, avail_w, mid)
        if n_lines * mid * LINE_HEIGHT_RATIO <= avail_h:
            lo = mid
        else:
            hi = mid
    return round(lo, 1)


def _find_floor(block: TextBlock, page_blocks: list[TextBlock], page_h: float) -> float:
    """Y boundary below this block — nearest block below that overlaps horizontally, or page bottom."""
    bx0, _, bx1, by1 = block.bbox
    floor = page_h - 5
    for other in page_blocks:
        if other is block:
            continue
        ox0, oy0, ox1, _ = other.bbox
        if oy0 > by1 and ox0 < bx1 and ox1 > bx0:
            floor = min(floor, oy0)
    return floor


def _find_ceiling(block: TextBlock, page_blocks: list[TextBlock]) -> float:
    """Y boundary above this block — nearest block above that overlaps horizontally, or page top."""
    bx0, by0, bx1, _ = block.bbox
    ceiling = 5.0
    for other in page_blocks:
        if other is block:
            continue
        ox0, _, ox1, oy1 = other.bbox
        if oy1 < by0 and ox0 < bx1 and ox1 > bx0:
            ceiling = max(ceiling, oy1)
    return ceiling


def overlay_translation(
    src_pdf: str | Path,
    blocks: list[TextBlock],
    translations: dict[str, str],
    output: str | Path,
    mode: Literal["below", "above", "replace"] = "below",
    font_path: str | Path | None = None,
    translation_font_size: float = 9.0,
) -> Path:
    src_pdf = Path(src_pdf)
    output = Path(output)
    if not src_pdf.exists():
        raise FileNotFoundError(f"Source PDF not found: {src_pdf}")

    resolved_font_path = _resolve_font_path(font_path)
    logger.info("Bilingual overlay: font=%s, blocks=%d, translations=%d, mode=%s",
                resolved_font_path or "built-in china-s", len(blocks), len(translations), mode)

    try:
        with fitz.open(src_pdf) as doc:
            blocks_by_page: dict[int, list[TextBlock]] = {}
            for block in blocks:
                blocks_by_page.setdefault(block.page, []).append(block)
            # Sort each page's blocks top-to-bottom, left-to-right
            for pnum in blocks_by_page:
                blocks_by_page[pnum].sort(key=lambda b: (b.bbox[1], b.bbox[0]))

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_blocks = blocks_by_page.get(page_num, [])
                if not page_blocks:
                    continue
                page_h = page.rect.height
                font_kw = _font_kwargs(resolved_font_path)

                if mode == "replace":
                    _apply_replace(page, page_blocks, translations, font_kw, translation_font_size)
                elif mode == "above":
                    _apply_above(page, page_blocks, translations, font_kw, translation_font_size)
                else:
                    _apply_below(page, page_blocks, translations, font_kw, translation_font_size, page_h)

            doc.save(str(output), garbage=4, deflate=True)
    except Exception as e:
        raise RuntimeError(f"PDF overlay failed: {e}") from e

    return output


def _apply_below(
    page: fitz.Page,
    page_blocks: list[TextBlock],
    translations: dict[str, str],
    font_kw: dict,
    base_size: float,
    page_h: float,
) -> None:
    for block in page_blocks:
        trans = translations.get(block.block_id)
        if not trans or not trans.strip():
            continue
        x0, y0, x1, y1 = block.bbox
        w = x1 - x0
        if w <= 0:
            continue

        floor = _find_floor(block, page_blocks, page_h)
        top = y1 + PAD_BELOW_ORIGINAL
        bottom = floor - PAD_ABOVE_NEXT
        avail_h = bottom - top
        if avail_h < MIN_FONT_SIZE * LINE_HEIGHT_RATIO:
            continue

        fs = _fit_font_size(trans, w, avail_h, base_size)
        rect = fitz.Rect(x0, top, x1, bottom)

        page.draw_rect(rect, color=None, fill=BG_COLOR, fill_opacity=0.9)
        page.draw_line(fitz.Point(x0, top), fitz.Point(x1, top),
                       color=SEPARATOR_COLOR, width=0.4)

        text_rect = fitz.Rect(x0 + 1.5, top + 1, x1 - 1, bottom - 0.5)
        page.insert_textbox(text_rect, trans, fontsize=fs,
                            color=TEXT_COLOR, align=fitz.TEXT_ALIGN_LEFT, **font_kw)


def _apply_above(
    page: fitz.Page,
    page_blocks: list[TextBlock],
    translations: dict[str, str],
    font_kw: dict,
    base_size: float,
) -> None:
    for block in page_blocks:
        trans = translations.get(block.block_id)
        if not trans or not trans.strip():
            continue
        x0, y0, x1, y1 = block.bbox
        w = x1 - x0
        if w <= 0:
            continue

        ceiling = _find_ceiling(block, page_blocks)
        bottom = y0 - PAD_BELOW_ORIGINAL
        top = ceiling + PAD_ABOVE_NEXT
        avail_h = bottom - top
        if avail_h < MIN_FONT_SIZE * LINE_HEIGHT_RATIO:
            continue

        fs = _fit_font_size(trans, w, avail_h, base_size)
        rect = fitz.Rect(x0, top, x1, bottom)

        page.draw_rect(rect, color=None, fill=BG_COLOR, fill_opacity=0.95)

        text_rect = fitz.Rect(x0 + 1.5, top + 0.5, x1 - 1, bottom - 1)
        page.insert_textbox(text_rect, trans, fontsize=fs,
                            color=TEXT_COLOR, align=fitz.TEXT_ALIGN_LEFT, **font_kw)


def _apply_replace(
    page: fitz.Page,
    page_blocks: list[TextBlock],
    translations: dict[str, str],
    font_kw: dict,
    base_size: float,
) -> None:
    for block in page_blocks:
        trans = translations.get(block.block_id)
        if not trans or not trans.strip():
            continue
        x0, y0, x1, y1 = block.bbox
        w, h = x1 - x0, y1 - y0
        if w <= 0:
            continue

        page.add_redact_annot(fitz.Rect(x0, y0, x1, y1), fill=(1, 1, 1))
        page.apply_redactions()

        fs = _fit_font_size(trans, w, h, base_size * 0.9)
        text_rect = fitz.Rect(x0, y0, x1, y1)
        page.insert_textbox(text_rect, trans, fontsize=fs,
                            color=(0.1, 0.1, 0.4), align=fitz.TEXT_ALIGN_LEFT, **font_kw)