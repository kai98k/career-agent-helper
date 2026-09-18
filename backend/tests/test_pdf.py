"""PDF 抽取的失敗路徑測試。

happy path 需要一份有文字的 PDF，而 repo 裡不放真實履歷，
所以這裡專測「壞掉的輸入會不會給出有用的錯誤訊息」——
那本來就是這個模組大部分的工作。
"""

from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.pdf import PdfExtractError, extract_text

LIMITS = {"max_bytes": 5 * 1_048_576, "max_pages": 10}


def _blank_pdf(pages: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=595, height=842)  # A4
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_empty_file():
    with pytest.raises(PdfExtractError, match="空的"):
        extract_text(b"", **LIMITS)


def test_too_large():
    with pytest.raises(PdfExtractError, match="超過上限"):
        extract_text(b"x" * 10, max_bytes=5, max_pages=10)


def test_not_a_pdf():
    with pytest.raises(PdfExtractError, match="不是有效的 PDF"):
        extract_text(b"this is just text, not a pdf", **LIMITS)


def test_too_many_pages():
    with pytest.raises(PdfExtractError, match="超過上限 2 頁"):
        extract_text(_blank_pdf(3), max_bytes=5 * 1_048_576, max_pages=2)


def test_scanned_pdf_has_no_text():
    """空白頁 = 抽不出文字，等同掃描檔。要回 422 並叫使用者改貼純文字。"""
    with pytest.raises(PdfExtractError, match="抽不出文字") as e:
        extract_text(_blank_pdf(1), **LIMITS)
    assert e.value.status_code == 422
