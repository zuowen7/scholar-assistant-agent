"""本地 OCR 兜底 — 无云端视觉 Key 时用 Tesseract / PaddleOCR 识别图片文字。

纯文本模型（如 deepseek-v4-flash）无法识图，此时 /api/vision/ocr 回退到
本地引擎：优先 Tesseract（快、需系统二进制），失败回退 PaddleOCR（自带模型）。
两个引擎都不可用时返回 None，由路由给出可操作提示。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 避免 PaddleOCR 首次实例化时的外部连通性检查拖慢识别
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def _try_tesseract(image_path: str | Path) -> str | None:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    try:
        text = pytesseract.image_to_string(Image.open(image_path), lang="eng+chi_sim")
        return text.strip() or None
    except Exception as exc:
        logger.info("Tesseract OCR 不可用（需安装系统 Tesseract）: %s", exc)
        return None


def _try_paddleocr(image_path: str | Path) -> str | None:
    try:
        import numpy as np
        from paddleocr import PaddleOCR
        from PIL import Image
    except ImportError:
        return None
    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", use_gpu=False, show_log=False)
        image = np.array(Image.open(image_path).convert("RGB"))
        result = ocr.ocr(image, cls=True)
        lines: list[str] = []
        for page in result or []:
            if not page:
                continue
            for item in page:
                payload = item[-1]
                text = payload[0] if isinstance(payload, (list, tuple)) else str(payload)
                lines.append(str(text))
        text = "\n".join(lines).strip()
        return text or None
    except Exception as exc:
        logger.info("PaddleOCR 失败: %s", exc)
        return None


def local_ocr_image(image_path: str | Path) -> tuple[str, str] | None:
    """本地识别图片文字，返回 (text, engine) 或 None（两个引擎都不可用）。"""
    path = Path(image_path)
    if not path.is_file():
        return None

    text = _try_tesseract(path)
    if text:
        logger.info("本地 OCR（tesseract）识别 %d 字符", len(text))
        return text, "tesseract"

    text = _try_paddleocr(path)
    if text:
        logger.info("本地 OCR（paddleocr）识别 %d 字符", len(text))
        return text, "paddleocr"

    return None
