"""扫描件 PDF OCR fallback，使用 PyMuPDF 逐页渲染。"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

# 触发 OCR 的阈值：平均每页提取字符数低于此值则认为可能是扫描件。
_OCR_CHAR_THRESHOLD = 100
_OCR_DPI = 200
_MIN_OCR_CHARS = 10
_DOMINANT_IMAGE_MIN_AREA_RATIO = 0.50
_DOMINANT_IMAGE_MIN_SHARE = 0.80
_PADDLE_V3_DETECTION_MODEL = "PP-OCRv5_mobile_det"
_PADDLE_V3_RECOGNITION_MODEL = "PP-OCRv5_mobile_rec"
_PAGE_MARKER_RE = re.compile(r"(?m)^\[Page\s+(\d+)\][ \t]*$")


@dataclass(frozen=True)
class OCRPage:
    """一页 OCR 结果；页码始终对应原 PDF 的 1-based 页码。"""

    page_num: int
    text: str
    engine: str
    rotation: int = 0


def is_likely_scanned(total_chars: int, page_count: int) -> bool:
    """判断 PDF 是否可能是扫描件。"""
    if page_count == 0:
        return False
    return total_chars / page_count < _OCR_CHAR_THRESHOLD


def parse_ocr_pages(text: str) -> dict[int, str]:
    """解析兼容格式 ``[Page N]``，不因空白页而压缩后续页码。"""
    matches = list(_PAGE_MARKER_RE.finditer(text))
    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages[int(match.group(1))] = text[match.end() : end].strip()
    return pages


def _format_ocr_pages(pages: Sequence[OCRPage]) -> str | None:
    if not pages:
        return None
    return "\n\n".join(f"[Page {page.page_num}]\n{page.text}" for page in pages)


def _recognized_character_count(pages: Sequence[OCRPage]) -> int:
    return sum(len(re.sub(r"\s+", "", page.text)) for page in pages)


def _dominant_image_clip(page: Any) -> Any | None:
    """若页面主要由一张图片构成，只渲染该图片区域以去除页边与水印。"""
    try:
        if page.get_text("text").strip():
            return None
    except Exception:
        # 文本探测失败不应阻断 OCR；继续根据图片布局保守判断。
        pass

    page_area = float(page.rect.width * page.rect.height)
    if page_area <= 0:
        return None

    largest_rect = None
    largest_area = 0.0
    total_image_area = 0.0
    try:
        for image_info in page.get_images(full=True):
            xref = image_info[0]
            for rect in page.get_image_rects(xref):
                clipped = rect & page.rect
                area = max(0.0, float(clipped.width)) * max(0.0, float(clipped.height))
                total_image_area += area
                if area > largest_area:
                    largest_rect = clipped
                    largest_area = area
    except Exception as exc:
        logger.debug("检测页面主图失败，改为渲染整页: %s", exc)
        return None

    if (
        largest_rect is not None
        and largest_area / page_area >= _DOMINANT_IMAGE_MIN_AREA_RATIO
        and largest_area / max(total_image_area, 1.0) >= _DOMINANT_IMAGE_MIN_SHARE
    ):
        return largest_rect
    return None


def _iter_pdf_page_images(
    pdf_path: str | Path,
    max_pages: int | None,
    *,
    dpi: int = _OCR_DPI,
) -> Iterator[tuple[int, Image.Image]]:
    """用 PyMuPDF 逐页渲染，避免 pdf2image/Poppler 依赖和全量图片驻留内存。"""
    import fitz
    from PIL import Image

    if max_pages is not None and max_pages <= 0:
        return

    with fitz.open(pdf_path) as document:
        page_limit = (
            document.page_count if max_pages is None else min(max_pages, document.page_count)
        )
        for page_index in range(page_limit):
            page = document.load_page(page_index)
            clip = _dominant_image_clip(page)
            pixmap = page.get_pixmap(
                dpi=dpi,
                colorspace=fitz.csRGB,
                alpha=False,
                clip=clip,
            )
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            yield page_index + 1, image


def _osd_rotation(osd: object) -> int:
    if isinstance(osd, Mapping):
        raw_rotation = osd.get("rotate", osd.get("Rotate", 0))
        try:
            rotation = int(raw_rotation)
        except (TypeError, ValueError):
            return 0
    else:
        match = re.search(r"(?im)^Rotate:\s*(\d+)\s*$", str(osd))
        rotation = int(match.group(1)) if match else 0
    return rotation if rotation in {90, 180, 270} else 0


def _orient_for_tesseract(image: Image.Image, pytesseract: Any) -> tuple[Image.Image, int]:
    """按 Tesseract OSD 建议纠正像素方向；OSD 不可用时保留原图。"""
    try:
        output = getattr(pytesseract, "Output", None)
        output_dict = getattr(output, "DICT", None)
        if output_dict is None:
            osd = pytesseract.image_to_osd(image)
        else:
            osd = pytesseract.image_to_osd(image, output_type=output_dict)
        rotation = _osd_rotation(osd)
    except Exception as exc:
        logger.debug("Tesseract 页面方向检测失败，使用原方向: %s", exc)
        return image, 0

    if rotation:
        # OSD 的 Rotate 表示需要顺时针旋转的角度；Pillow 正角度为逆时针。
        return image.rotate(-rotation, expand=True), rotation
    return image, 0


def _tesseract_pages(pdf_path: str | Path, max_pages: int | None) -> list[OCRPage]:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception:
        return []

    pages: list[OCRPage] = []
    try:
        logger.info("触发 Tesseract OCR fallback（%s）", pdf_path)
        for page_num, image in _iter_pdf_page_images(pdf_path, max_pages):
            oriented = image
            try:
                oriented, rotation = _orient_for_tesseract(image, pytesseract)
                text = pytesseract.image_to_string(oriented, lang="eng+chi_sim").strip()
                pages.append(OCRPage(page_num, text, "tesseract", rotation))
            except Exception as exc:
                logger.warning("Tesseract OCR 第 %d 页失败: %s", page_num, exc)
                pages.append(OCRPage(page_num, "", "tesseract"))
            finally:
                if oriented is not image:
                    oriented.close()
                image.close()
    except Exception as exc:
        logger.warning("Tesseract OCR 失败: %s", exc)
    return pages


def _extract_paddle_text(result: object) -> list[str]:
    """兼容 PaddleOCR 3.x ``rec_texts`` 与 2.x 嵌套 tuple 返回值。"""
    lines: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            if "rec_texts" in value:
                rec_texts = value["rec_texts"]
                if isinstance(rec_texts, str):
                    if rec_texts.strip():
                        lines.append(rec_texts.strip())
                elif isinstance(rec_texts, Sequence):
                    lines.extend(str(text).strip() for text in rec_texts if str(text).strip())
                return
            for nested in value.values():
                visit(nested)
            return

        if not isinstance(value, (list, tuple)):
            return

        # PaddleOCR 2.x 的单行结构通常是 [box, (text, score)]。
        if len(value) >= 2 and isinstance(value[-1], (list, tuple)):
            recognition = value[-1]
            if recognition and isinstance(recognition[0], str):
                text = recognition[0].strip()
                if text:
                    lines.append(text)
                return

        for nested in value:
            visit(nested)

    visit(result)
    return lines


def _paddle_major_version(paddleocr_module: Any) -> int:
    match = re.match(r"(\d+)", str(getattr(paddleocr_module, "__version__", "")))
    return int(match.group(1)) if match else 3


def _paddle_cpu_runtime_issue(paddle_module: Any | None = None) -> str | None:
    """返回已知会破坏 PaddleOCR CPU 推理的 PaddlePaddle 版本说明。"""
    try:
        if paddle_module is None:
            import paddle as paddle_module
    except Exception:
        return None

    version = str(getattr(paddle_module, "__version__", ""))
    match = re.match(r"(\d+)\.(\d+)", version)
    if match and (int(match.group(1)), int(match.group(2))) == (3, 3):
        return (
            f"PaddlePaddle {version} 的 CPU 推理存在已知 oneDNN/PIR 回归；"
            "请按 requirements-ocr.txt 使用 3.2.0"
        )
    return None


def _paddleocr_pages(pdf_path: str | Path, max_pages: int | None) -> list[OCRPage]:
    # 避免每次启动时检查远端模型源；缺失模型时引擎仍会按自身规则报错或下载。
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        import numpy as np
    except Exception as exc:
        logger.debug("PaddleOCR 的 NumPy 依赖不可用: %s", exc)
        return []

    try:
        import paddleocr as paddleocr_module
        from paddleocr import PaddleOCR
    except Exception as exc:
        logger.debug("PaddleOCR 不可用: %s", exc)
        return []

    # Windows 下 Paddle 会改变 DLL 搜索状态；先让 PaddleOCR 的可选后端完成
    # 导入，再读取 Paddle 版本，可避免其间接依赖 Torch 时发生 DLL 冲突。
    try:
        import paddle as paddle_module
    except Exception as exc:
        logger.debug("PaddlePaddle 不可用: %s", exc)
        return []

    runtime_issue = _paddle_cpu_runtime_issue(paddle_module)
    if runtime_issue:
        logger.warning(runtime_issue)
        return []

    major_version = _paddle_major_version(paddleocr_module)
    try:
        if major_version >= 3:
            engine = PaddleOCR(
                # 官方 mobile 模型面向边缘/桌面部署，并直接覆盖中英混排；显式
                # 指定模型后 PaddleOCR 会忽略 lang，因此这里不再传 lang。
                text_detection_model_name=_PADDLE_V3_DETECTION_MODEL,
                text_recognition_model_name=_PADDLE_V3_RECOGNITION_MODEL,
                use_doc_orientation_classify=True,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
            )
        else:
            engine = PaddleOCR(
                lang="ch",
                use_angle_cls=True,
                use_gpu=False,
                show_log=False,
            )
    except Exception as exc:
        logger.warning("PaddleOCR 初始化失败: %s", exc)
        return []

    pages: list[OCRPage] = []
    try:
        logger.info("触发 PaddleOCR fallback（%s）", pdf_path)
        for page_num, image in _iter_pdf_page_images(pdf_path, max_pages):
            try:
                rgb = np.asarray(image.convert("RGB"))
                bgr = rgb[:, :, ::-1].copy()
                result = engine.predict(bgr) if major_version >= 3 else engine.ocr(bgr, cls=True)
                text = "\n".join(_extract_paddle_text(result)).strip()
                pages.append(OCRPage(page_num, text, "paddleocr"))
            except Exception as exc:
                logger.warning("PaddleOCR 第 %d 页失败: %s", page_num, exc)
                pages.append(OCRPage(page_num, "", "paddleocr"))
            finally:
                image.close()
    except Exception as exc:
        logger.warning("PaddleOCR 失败: %s", exc)
    return pages


def _try_tesseract(pdf_path: str | Path, max_pages: int | None = 5) -> str | None:
    """兼容旧调用：使用 Tesseract 返回带页码标记的文字。"""
    return _format_ocr_pages(_tesseract_pages(pdf_path, max_pages))


def _try_paddleocr(pdf_path: str | Path, max_pages: int | None = 5) -> str | None:
    """兼容旧调用：使用 PaddleOCR 返回带页码标记的文字。"""
    return _format_ocr_pages(_paddleocr_pages(pdf_path, max_pages))


def ocr_pdf_pages(pdf_path: str | Path, max_pages: int | None = 20) -> list[OCRPage]:
    """执行 OCR 并返回结构化逐页结果；``None`` 表示处理全部页面。"""
    pdf_path = Path(pdf_path)

    # 中文课件优先使用 PaddleOCR；不可用或有效文字过少时回退 Tesseract。
    pages = _paddleocr_pages(pdf_path, max_pages)
    if _recognized_character_count(pages) >= _MIN_OCR_CHARS:
        logger.info("PaddleOCR 成功，提取 %d 个非空白字符", _recognized_character_count(pages))
        return pages

    pages = _tesseract_pages(pdf_path, max_pages)
    if _recognized_character_count(pages) >= _MIN_OCR_CHARS:
        logger.info("Tesseract OCR 成功，提取 %d 个非空白字符", _recognized_character_count(pages))
        return pages

    logger.warning("所有 OCR 引擎均失败或未识别出足够文字")
    return []


def ocr_pdf(pdf_path: str | Path, max_pages: int | None = 20) -> str | None:
    """兼容旧合同：返回 ``[Page N]`` 格式文字，失败返回 ``None``。"""
    return _format_ocr_pages(ocr_pdf_pages(pdf_path, max_pages=max_pages))


def ocr_availability() -> list[str]:
    """探测可导入的 OCR 引擎；Paddle 模型是否齐全需在实际识别时验证。"""
    engines: list[str] = []
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        engines.append("tesseract")
    except Exception:
        pass

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        import paddleocr  # noqa: F401

        if _paddle_cpu_runtime_issue() is None:
            engines.append("paddleocr")
    except Exception:
        pass
    return engines


def ocr_install_hint() -> str:
    """面向用户的扫描版 PDF OCR 提示。"""
    engines = ocr_availability()
    if engines:
        return (
            f"OCR 引擎（{'、'.join(engines)}）可用，但未识别出足够文字；"
            "请确认 PDF 清晰度与本地 OCR 模型是否完整"
        )
    runtime_issue = _paddle_cpu_runtime_issue()
    if runtime_issue:
        return runtime_issue
    return (
        "扫描版 PDF 需要先安装 OCR 依赖：pip install -r requirements-ocr.txt"
        "（Tesseract 还需安装系统程序及 eng/chi_sim 语言包）"
    )
