"""텍스트 추출과 '검사 불가(fail-closed)' 판정."""
import io

from docx import Document
from PIL import Image

from backend.app.extract import extract_text


def test_txt_utf8_and_cp949():
    assert extract_text("a.txt", "안녕".encode("utf-8")).text == "안녕"
    assert extract_text("a.txt", "안녕".encode("cp949")).text == "안녕"


def test_docx_reads_tables():
    doc = Document()
    t = doc.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "연락처", "010-2222-3333"
    buf = io.BytesIO(); doc.save(buf)
    ex = extract_text("a.docx", buf.getvalue())
    assert ex.readable and "010-2222-3333" in ex.text


def test_image_only_pdf_is_unreadable():
    buf = io.BytesIO(); Image.new("RGB", (400, 200), "white").save(buf, "PDF")
    ex = extract_text("scan.pdf", buf.getvalue())
    assert ex.readable is False


def test_unsupported_and_broken_files_are_unreadable():
    assert extract_text("a.hwp", b"xx").readable is False
    assert extract_text("a.pdf", b"not a pdf").readable is False
