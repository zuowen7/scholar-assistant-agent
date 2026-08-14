"""parser.ocr — 扫描件检测、OCR 环境探测与安装提示单元测试"""

import types

from src.parser.ocr import is_likely_scanned, ocr_availability, ocr_install_hint


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
        fake_pdf2image = types.ModuleType("pdf2image")
        fake_pdf2image.convert_from_path = lambda *a, **k: None

        def fake_import(name, *args, **kwargs):
            if name == "pytesseract":
                return fake_pytesseract
            if name == "pdf2image":
                return fake_pdf2image
            raise ImportError(name)

        monkeypatch.setattr("builtins.__import__", fake_import)
        assert ocr_availability() == ["tesseract"]

    def test_paddleocr_detected_when_installed(self, monkeypatch):
        fake_paddleocr = types.ModuleType("paddleocr")
        fake_pdf2image = types.ModuleType("pdf2image")
        fake_pdf2image.convert_from_path = lambda *a, **k: None

        def fake_import(name, *args, **kwargs):
            if name == "paddleocr":
                return fake_paddleocr
            if name == "pdf2image":
                return fake_pdf2image
            raise ImportError(name)

        monkeypatch.setattr("builtins.__import__", fake_import)
        assert ocr_availability() == ["paddleocr"]


class TestOcrInstallHint:
    def test_hint_when_deps_installed_but_ocr_failed(self, monkeypatch):
        monkeypatch.setattr("src.parser.ocr.ocr_availability", lambda: ["tesseract"])
        hint = ocr_install_hint()
        assert "已就绪" in hint
        assert "清晰度" in hint

    def test_hint_when_no_deps(self, monkeypatch):
        monkeypatch.setattr("src.parser.ocr.ocr_availability", lambda: [])
        hint = ocr_install_hint()
        assert "requirements-ocr.txt" in hint
        assert "Tesseract" in hint
