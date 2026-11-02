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


# ---- OCR (스캔 PDF·이미지) ----
import random  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PIL import ImageDraw, ImageFilter, ImageFont  # noqa: E402

from backend.app import ocr  # noqa: E402
from backend.app.detect import detect  # noqa: E402

FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
needs_ocr = pytest.mark.skipif(not (ocr.available() and FONT.exists()), reason="Tesseract(kor) 또는 한글 글꼴 없음")
LINES = ["[인사발령 통보 - 내부용]", "주민등록번호: 950312-2345678", "연락처: 010-9876-5432 / yunseul.d@example.com",
         "급여 이체 계좌: 신한 110-234-567890", "영업팀 길하람 사원은 지난주 공황장애 진단을 받았다."]


def _scan(lines=LINES, noise=20000):
    """기울기·번짐·잡티를 넣은 가짜 스캔 이미지 (A4, 200dpi)."""
    font = ImageFont.truetype(str(FONT), 30, index=1)
    img = Image.new("L", (1654, 2339), 255)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((120, 120 + 48 * i), line, font=font, fill=20)
    img = img.rotate(0.8, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
    px = img.load(); rnd = random.Random(1)
    for _ in range(noise):
        px[rnd.randrange(img.width), rnd.randrange(img.height)] = rnd.randrange(150, 255)
    return img


@needs_ocr
def test_scanned_pdf_is_read_by_ocr_and_pii_detected():
    buf = io.BytesIO(); _scan().convert("RGB").save(buf, "PDF", resolution=200)
    ex = extract_text("scan.pdf", buf.getvalue())
    assert ex.readable and ex.kind == "pdf-ocr" and ex.ocr_confidence >= ocr.MIN_CONFIDENCE
    found = {(e.type, e.text) for e in detect(ex.text)}
    assert {("RRN", "950312-2345678"), ("PHONE", "010-9876-5432"), ("ACCOUNT", "110-234-567890")} <= found
    assert "공황장애" in ex.text.replace(" ", "")


@needs_ocr
def test_image_file_is_read_by_ocr():
    buf = io.BytesIO(); _scan().save(buf, "PNG")
    ex = extract_text("photo.png", buf.getvalue())
    assert ex.readable and ex.kind == "image-ocr" and "950312-2345678" in ex.text


@needs_ocr
def test_unreadable_noise_image_is_blocked():
    img = Image.effect_noise((800, 600), 120).convert("L")
    buf = io.BytesIO(); img.save(buf, "PNG")
    assert extract_text("noise.png", buf.getvalue()).readable is False


@needs_ocr
def test_too_many_scanned_pages_is_blocked():
    pages = [Image.new("RGB", (200, 200), "white") for _ in range(ocr.MAX_PAGES + 1)]
    buf = io.BytesIO(); pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:])
    ex = extract_text("long.pdf", buf.getvalue())
    assert ex.readable is False and "한도" in ex.reason
