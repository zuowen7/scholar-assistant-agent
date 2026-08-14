"""扫描件 OCR fallback — 当 PDF 文本提取质量过低时触发"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 触发 OCR 的阈值: 平均每页提取字符数低于此值则认为是扫描件
_OCR_CHAR_THRESHOLD = 100  # 字符/页


def is_likely_scanned(total_chars: int, page_count: int) -> bool:
    """判断 PDF 是否可能是扫描件"""
    if page_count == 0:
        return False
    avg_chars = total_chars / page_count
    return avg_chars < _OCR_CHAR_THRESHOLD


def _try_tesseract(pdf_path: str | Path, max_pages: int = 5) -> str | None:
    """使用 Tesseract OCR（通过 pytesseract）提取文字"""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return None

    try:
        logger.info("触发 Tesseract OCR fallback（%s）", pdf_path)
        # 将 PDF 转为图片列表
        images = convert_from_path(str(pdf_path), dpi=200, first_page=1, last_page=max_pages)
        text_parts: list[str] = []
        for i, img in enumerate(images, 1):
            page_text = pytesseract.image_to_string(img, lang="eng+chi_sim")
            if page_text:
                text_parts.append(f"[Page {i}]\n{page_text}")
        return "\n\n".join(text_parts) if text_parts else None
    except Exception as e:
        logger.warning("Tesseract OCR 失败: %s", e)
        return None


def _try_paddleocr(pdf_path: str | Path, max_pages: int = 5) -> str | None:
    """使用 PaddleOCR 提取文字"""
    try:
        from paddleocr import PaddleOCR
        from pdf2image import convert_from_path
    except ImportError:
        return None

    try:
        logger.info("触发 PaddleOCR fallback（%s）", pdf_path)
        images = convert_from_path(str(pdf_path), dpi=200, first_page=1, last_page=max_pages)
        ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
        text_parts: list[str] = []
        for i, img in enumerate(images, 1):
            result = ocr.ocr(img, cls=True)
            if result and result[0]:
                lines = []
                for line in result[0]:
                    txt = line[-1][0] if isinstance(line[-1], tuple) else str(line)
                    if isinstance(txt, list):
                        txt = " ".join(
                            part[0] if isinstance(part, tuple) else str(part) for part in txt
                        )
                    lines.append(str(txt))
                text_parts.append(f"[Page {i}]\n" + "\n".join(lines))
        return "\n\n".join(text_parts) if text_parts else None
    except Exception as e:
        logger.warning("PaddleOCR 失败: %s", e)
        return None


def ocr_pdf(pdf_path: str | Path, max_pages: int = 20) -> str | None:
    """对 PDF 执行 OCR，返回提取的文字（失败返回 None）

    优先级: Tesseract → PaddleOCR
    仅处理前 max_pages 页以控制耗时。
    """
    pdf_path = Path(pdf_path)

    # Tesseract
    text = _try_tesseract(pdf_path, max_pages=max_pages)
    if text and len(text.strip()) > 50:
        logger.info("Tesseract OCR 成功，提取 %d 字符", len(text))
        return text

    # PaddleOCR
    text = _try_paddleocr(pdf_path, max_pages=max_pages)
    if text and len(text.strip()) > 50:
        logger.info("PaddleOCR 成功，提取 %d 字符", len(text))
        return text

    logger.warning("所有 OCR 引擎均失败，返回 None")
    return None


def ocr_availability() -> list[str]:
    """探测当前环境可用的 OCR 引擎，返回引擎名列表（'tesseract' / 'paddleocr'）"""
    engines: list[str] = []
    try:
        import pytesseract
        from pdf2image import convert_from_path  # noqa: F401

        # pip 包存在还不够，Tesseract 还需要系统二进制
        pytesseract.get_tesseract_version()
        engines.append("tesseract")
    except Exception:
        pass
    try:
        import paddleocr  # noqa: F401
        from pdf2image import convert_from_path  # noqa: F401

        engines.append("paddleocr")
    except Exception:
        pass
    return engines


def ocr_install_hint() -> str:
    """面向用户的扫描版 PDF OCR 提示（区分已装依赖/未装依赖两种情况）"""
    engines = ocr_availability()
    if engines:
        return (
            f"OCR 引擎（{'、'.join(engines)}）已就绪但未能识别出文字，"
            "请确认 PDF 清晰度，或改用云端翻译/其他文献"
        )
    return (
        "扫描版 PDF 需要先安装 OCR 依赖：pip install -r requirements-ocr.txt"
        "（Tesseract 引擎还需安装系统 Tesseract 及 eng/chi_sim 语言包）"
    )
