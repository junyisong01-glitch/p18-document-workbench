import pymupdf as fitz

from app import parser
from app.admission import categories
from app.chunking import units_from
from app.pdf_ocr import OcrError


def fixture_pdf(path, *, mixed=False):
    with fitz.open() as source, fitz.open() as output:
        source.new_page().insert_text((72, 100), "Rasterized acceptance report")
        if mixed:
            output.new_page().insert_text((72, 100), "Native overview")
        scan = output.new_page()
        scan.insert_image(scan.rect, pixmap=source[0].get_pixmap())
        if mixed:
            output.new_page()
        output.save(path)


def test_ocr_only_reads_scan_pages_and_keeps_original_page_anchor(tmp_path, monkeypatch):
    calls = []

    def recognize(self, page):
        calls.append(page.number)
        return [{"text": "最大重连耗时 8.5 秒", "confidence": 0.98}]

    monkeypatch.setattr(parser.PdfOcr, "recognize", recognize)
    path = tmp_path / "original.pdf"
    fixture_pdf(path, mixed=True)
    result = parser.process(tmp_path, ".pdf")
    assert calls == [1]
    assert result["issues"] == []
    assert result["preview"]["original"] == "original.pdf"
    assert [p["extraction"] for p in result["pages"]] == ["text", "ocr", "text"]
    assert result["pages"][2]["blank"]
    units, _ = units_from({"ext": ".pdf", "result": result})
    hit = next(unit for unit in units if "8.5" in unit["text"])
    assert hit["sources"][0]["page"] == 2


def test_uncertain_ocr_enters_technical_review(tmp_path, monkeypatch):
    path = tmp_path / "original.pdf"
    fixture_pdf(path)
    monkeypatch.setattr(parser.PdfOcr, "recognize", lambda *_: [{"text": "测试结果", "confidence": 0.35}])
    result = parser.process(tmp_path, ".pdf")
    assert result["issues"][0]["page"] == 1
    assert categories({"result": result, "state": "review", "characters": result["characters"]}) == ["text"]


def test_unavailable_ocr_retains_native_text_but_reports_incomplete(tmp_path, monkeypatch):
    def unavailable(*_):
        raise OcrError("此环境的本地 OCR 不可用。")

    monkeypatch.setattr(parser.PdfOcr, "recognize", unavailable)
    fixture_pdf(tmp_path / "original.pdf", mixed=True)
    result = parser.process(tmp_path, ".pdf")
    assert result["blocks"][0]["text"] == "Native overview"
    assert result["issues"][0]["page"] == 2
    assert categories({"result": result, "state": "review", "characters": result["characters"]}) == ["missing"]
    assert "error" not in result


def test_completely_unreadable_scan_cannot_advance(tmp_path, monkeypatch):
    monkeypatch.setattr(parser.PdfOcr, "recognize", lambda *_: [])
    fixture_pdf(tmp_path / "original.pdf")
    result = parser.process(tmp_path, ".pdf")
    assert result["characters"] == 0
    assert "OCR 未识别到文字" in result["error"]
