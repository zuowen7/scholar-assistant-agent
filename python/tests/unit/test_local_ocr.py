"""本地 OCR 兜底（Tesseract / PaddleOCR）单元测试。"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from src.mcp.local_ocr import _try_paddleocr, _try_tesseract, local_ocr_image


def _make_png(tmp_path) -> Path:
    """生成一张真实可完整解码的 PNG（Image.open 是惰性的，必须能通过 .convert() 解码）。"""
    from PIL import Image

    img = tmp_path / "page.png"
    Image.new("RGB", (16, 16), "white").save(img)
    return img


def _fake_tesseract_module(text: str | None):
    mod = ModuleType("pytesseract")
    mod.image_to_string = MagicMock(return_value=text or "")
    return mod


def _fake_paddleocr_module(lines: list[str] | None):
    mod = ModuleType("paddleocr")
    fake_ocr = MagicMock()
    page = [[None, (line, 0.99)] for line in (lines or [])]
    fake_ocr.ocr.return_value = [page]
    mod.PaddleOCR = MagicMock(return_value=fake_ocr)
    return mod


class TestLocalOcr:
    def test_tesseract_success(self, tmp_path):
        img = _make_png(tmp_path)
        with patch.dict(sys.modules, {"pytesseract": _fake_tesseract_module("识别出的文字")}):
            result = local_ocr_image(img)
        assert result == ("识别出的文字", "tesseract")

    def test_tesseract_empty_falls_back_to_paddle(self, tmp_path):
        img = _make_png(tmp_path)
        with patch.dict(
            sys.modules,
            {
                "pytesseract": _fake_tesseract_module(""),
                "paddleocr": _fake_paddleocr_module(["第一行", "第二行"]),
            },
        ):
            result = local_ocr_image(img)
        assert result == ("第一行\n第二行", "paddleocr")

    def test_tesseract_import_error_falls_back_to_paddle(self, tmp_path):
        img = _make_png(tmp_path)
        with patch.dict(
            sys.modules,
            {"pytesseract": None, "paddleocr": _fake_paddleocr_module(["仅 Paddle 可用"])},
        ):
            # pytesseract 未安装 → ImportError → 回退 PaddleOCR
            result = local_ocr_image(img)
        assert result == ("仅 Paddle 可用", "paddleocr")

    def test_both_engines_unavailable_returns_none(self, tmp_path):
        img = _make_png(tmp_path)
        with patch.dict(sys.modules, {"pytesseract": None, "numpy": None, "paddleocr": None}):
            result = local_ocr_image(img)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        assert local_ocr_image(tmp_path / "missing.png") is None

    def test_tesseract_exception_returns_none(self, tmp_path):
        img = _make_png(tmp_path)
        mod = _fake_tesseract_module("x")
        mod.image_to_string = MagicMock(side_effect=RuntimeError("tesseract binary missing"))
        with patch.dict(sys.modules, {"pytesseract": mod}):
            assert _try_tesseract(img) is None

    def test_paddle_handles_flat_string_payload(self, tmp_path):
        img = _make_png(tmp_path)
        mod = ModuleType("paddleocr")
        fake_ocr = MagicMock()
        fake_ocr.ocr.return_value = [[[None, "扁平字符串"]]]
        mod.PaddleOCR = MagicMock(return_value=fake_ocr)
        with patch.dict(sys.modules, {"paddleocr": mod}):
            assert _try_paddleocr(img) == "扁平字符串"
