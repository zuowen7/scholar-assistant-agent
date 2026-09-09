"""parser.ocr — 扫描件检测、逐页渲染、方向纠正与引擎兼容测试。"""

import builtins
import sys
import types
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

from src.parser.ocr import (
    OCRPage,
    _dominant_image_clip,
    _extract_paddle_text,
    _iter_pdf_page_images,
    _paddle_cpu_runtime_issue,
    _try_paddleocr,
    _try_tesseract,
    is_likely_scanned,
    ocr_availability,
    ocr_install_hint,
    ocr_pdf,
    parse_ocr_pages,
)


class TestIsLikelyScanned:
    def test_empty_pdf_not_scanned(self):
        assert not is_likely_scanned(total_chars=0, page_count=0)

    def test_rich_text_not_scanned(self):
        assert not is_likely_scanned(total_chars=10_000, page_count=10)

    def test_sparse_text_is_scanned(self):
        assert is_likely_scanned(total_chars=200, page_count=10)

    def test_threshold_boundary(self):
        # 平均每页 100 字符恰好不触发（阈值是 < 100）
        assert not is_likely_scanned(total_chars=1000, page_count=10)
        assert is_likely_scanned(total_chars=999, page_count=10)


class TestOcrAvailability:
    def test_no_engines_when_deps_missing(self, monkeypatch):
        def fake_import(name, *args, **kwargs):
            raise ImportError(name)

        monkeypatch.setattr("builtins.__import__", fake_import)
        assert ocr_availability() == []

    def test_tesseract_detected_when_binary_present(self, monkeypatch):
        fake_pytesseract = types.ModuleType("pytesseract")
        fake_pytesseract.get_tesseract_version = lambda: "5.3.0"

        def fake_import(name, *args, **kwargs):
            if name == "pytesseract":
                return fake_pytesseract
            raise ImportError(name)

        monkeypatch.setattr("builtins.__import__", fake_import)
        assert ocr_availability() == ["tesseract"]

    def test_paddleocr_detected_when_installed(self, monkeypatch):
        fake_paddleocr = types.ModuleType("paddleocr")
        fake_paddle = types.ModuleType("paddle")
        fake_paddle.__version__ = "3.2.0"

        def fake_import(name, *args, **kwargs):
            if name == "paddleocr":
                return fake_paddleocr
            if name == "paddle":
                return fake_paddle
            raise ImportError(name)

        monkeypatch.setattr("builtins.__import__", fake_import)
        assert ocr_availability() == ["paddleocr"]


class TestOcrInstallHint:
    def test_hint_when_deps_installed_but_ocr_failed(self, monkeypatch):
        monkeypatch.setattr("src.parser.ocr.ocr_availability", lambda: ["tesseract"])
        hint = ocr_install_hint()
        assert "可用" in hint
        assert "模型" in hint

    def test_hint_when_no_deps(self, monkeypatch):
        monkeypatch.setattr("src.parser.ocr.ocr_availability", lambda: [])
        monkeypatch.setattr("src.parser.ocr._paddle_cpu_runtime_issue", lambda: None)
        hint = ocr_install_hint()
        assert "requirements-ocr.txt" in hint
        assert "Tesseract" in hint


class TestPageContract:
    def test_page_markers_preserve_missing_middle_page(self):
        text = "[Page 1]\n第一页\n\n[Page 3]\n第三页"
        assert parse_ocr_pages(text) == {1: "第一页", 3: "第三页"}

    def test_legacy_ocr_pdf_format_is_preserved(self, monkeypatch):
        pages = [OCRPage(1, "第一页", "paddleocr"), OCRPage(3, "第三页", "paddleocr")]
        monkeypatch.setattr("src.parser.ocr.ocr_pdf_pages", lambda *args, **kwargs: pages)
        assert ocr_pdf("ignored.pdf") == "[Page 1]\n第一页\n\n[Page 3]\n第三页"


class TestPyMuPdfRendering:
    def test_renders_pdf_without_pdf2image(self, tmp_path):
        import fitz

        source = Image.new("RGB", (100, 200), "white")
        stream = BytesIO()
        source.save(stream, format="PNG")
        pdf_path = tmp_path / "image-only.pdf"

        document = fitz.open()
        page = document.new_page(width=100, height=200)
        page.insert_image(page.rect, stream=stream.getvalue())
        document.save(pdf_path)
        document.close()

        rendered = list(_iter_pdf_page_images(pdf_path, max_pages=None, dpi=72))

        assert len(rendered) == 1
        page_num, image = rendered[0]
        assert page_num == 1
        assert image.size == (100, 200)
        image.close()

    def test_page_with_selectable_text_is_not_cropped(self):
        page = MagicMock()
        page.get_text.return_value = "selectable text"

        assert _dominant_image_clip(page) is None
        page.get_images.assert_not_called()

    def test_multiple_meaningful_images_use_full_page(self):
        import fitz

        page = MagicMock()
        page.get_text.return_value = ""
        page.rect = fitz.Rect(0, 0, 100, 100)
        page.get_images.return_value = [(1,), (2,)]
        page.get_image_rects.side_effect = [
            [fitz.Rect(0, 0, 100, 60)],
            [fitz.Rect(0, 60, 100, 100)],
        ]

        assert _dominant_image_clip(page) is None


class TestTesseractCompatibility:
    def test_osd_rotation_is_applied_clockwise(self, monkeypatch):
        fake = types.ModuleType("pytesseract")
        fake.get_tesseract_version = lambda: "5.3.0"
        fake.image_to_osd = lambda image: {"rotate": 90}
        seen: dict[str, tuple[int, int]] = {}

        def image_to_string(image, **kwargs):
            seen["size"] = image.size
            return "方向已经纠正"

        fake.image_to_string = image_to_string
        monkeypatch.setattr(
            "src.parser.ocr._iter_pdf_page_images",
            lambda *args, **kwargs: iter([(7, Image.new("RGB", (10, 20), "white"))]),
        )

        with patch.dict(sys.modules, {"pytesseract": fake}):
            text = _try_tesseract("ignored.pdf", max_pages=1)

        assert text == "[Page 7]\n方向已经纠正"
        assert seen["size"] == (20, 10)

    def test_osd_failure_keeps_original_orientation(self, monkeypatch):
        fake = types.ModuleType("pytesseract")
        fake.get_tesseract_version = lambda: "5.3.0"
        fake.image_to_osd = MagicMock(side_effect=RuntimeError("no osd model"))
        fake.image_to_string = MagicMock(return_value="仍可识别")
        monkeypatch.setattr(
            "src.parser.ocr._iter_pdf_page_images",
            lambda *args, **kwargs: iter([(1, Image.new("RGB", (10, 20), "white"))]),
        )

        with patch.dict(sys.modules, {"pytesseract": fake}):
            assert _try_tesseract("ignored.pdf") == "[Page 1]\n仍可识别"
        assert fake.image_to_string.call_args.args[0].size == (10, 20)


class TestPaddleCompatibility:
    def test_rejects_known_bad_paddle_cpu_runtime(self):
        fake_paddle = types.SimpleNamespace(__version__="3.3.1")
        assert "已知" in _paddle_cpu_runtime_issue(fake_paddle)

    def test_accepts_documented_paddle_cpu_runtime(self):
        fake_paddle = types.SimpleNamespace(__version__="3.2.0")
        assert _paddle_cpu_runtime_issue(fake_paddle) is None

    def test_extracts_v3_dict_results(self):
        result = [{"rec_texts": ["光纤", "通信"], "rec_scores": [0.99, 0.98]}]
        assert _extract_paddle_text(result) == ["光纤", "通信"]

    def test_extracts_v2_tuple_results(self):
        result = [[[None, ("第一行", 0.99)], [None, ("第二行", 0.98)]]]
        assert _extract_paddle_text(result) == ["第一行", "第二行"]

    def test_uses_paddle_v3_api_and_chinese_model(self, monkeypatch):
        fake_module = types.ModuleType("paddleocr")
        fake_module.__version__ = "3.4.0"
        engine = MagicMock()
        engine.predict.return_value = [{"rec_texts": ["光纤", "通信"]}]
        constructor = MagicMock(return_value=engine)
        fake_module.PaddleOCR = constructor
        fake_paddle = types.ModuleType("paddle")
        fake_paddle.__version__ = "3.2.0"
        monkeypatch.setattr(
            "src.parser.ocr._iter_pdf_page_images",
            lambda *args, **kwargs: iter([(4, Image.new("RGB", (12, 8), "white"))]),
        )

        with patch.dict(sys.modules, {"paddleocr": fake_module, "paddle": fake_paddle}):
            text = _try_paddleocr("ignored.pdf", max_pages=1)

        assert text == "[Page 4]\n光纤\n通信"
        assert constructor.call_args.kwargs == {
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "text_recognition_model_name": "PP-OCRv5_mobile_rec",
            "use_doc_orientation_classify": True,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "device": "cpu",
        }
        engine.predict.assert_called_once()

    def test_import_oserror_is_treated_as_unavailable(self, monkeypatch):
        real_import = builtins.__import__
        fake_paddle = types.ModuleType("paddle")
        fake_paddle.__version__ = "3.2.0"

        def fake_import(name, *args, **kwargs):
            if name == "paddleocr":
                raise OSError("native library could not be loaded")
            if name == "paddle":
                return fake_paddle
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert _try_paddleocr("ignored.pdf") is None
