"""파일에서 텍스트를 추출한다.

원칙: 내용을 확인할 수 없으면 readable=False 로 돌려준다.
판정 단계에서 readable=False 는 규정 7-1에 따라 모든 수신자에게 차단된다(fail-closed).
스캔 PDF와 이미지(PNG·JPG)는 OCR로 읽고, 인식 신뢰도가 낮으면 읽기 불가로 처리한다.
"""
import io
from dataclasses import dataclass

from . import ocr

from docx import Document
from pypdf import PdfReader

# 페이지당 평균 글자 수가 이보다 적으면 "스캔 이미지 PDF"로 본다.
MIN_CHARS_PER_PAGE = 20


@dataclass
class Extracted:
    text: str
    readable: bool
    reason: str = ""      # readable=False 인 이유 (화면·로그 표시용)
    kind: str = ""        # txt / docx / pdf / pdf-ocr / image-ocr
    ocr_confidence: float | None = None   # OCR로 읽은 경우 평균 인식 신뢰도(0~100)


def _from_txt(data: bytes) -> str:
    # 한국어 문서는 UTF-8 외에 CP949(EUC-KR)로 저장된 경우가 많다.
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("텍스트 인코딩을 알 수 없음")


def _from_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    # 표 안의 글자도 개인정보가 자주 들어가는 곳이라 함께 읽는다.
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _from_pdf(data: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), max(len(pages), 1)


IMAGE_EXT = {"png", "jpg", "jpeg"}


def _ocr(images_fn, kind: str) -> Extracted:
    """OCR 결과를 신뢰도·글자 수 기준으로 검사해 Extracted로 만든다."""
    if not ocr.available():
        return Extracted("", False, "스캔 문서·이미지는 OCR이 필요하지만 이 서버에 OCR이 없음", kind)
    images = images_fn()
    text, conf = ocr.read_images(images)
    visible = len("".join(text.split()))
    if visible < MIN_CHARS_PER_PAGE * max(len(images), 1):
        return Extracted(text, False, "OCR로도 글자를 거의 읽지 못함 (빈 페이지·사진 등)", kind, round(conf, 1))
    if conf < ocr.MIN_CONFIDENCE:
        return Extracted(text, False, f"OCR 인식 신뢰도 낮음 ({conf:.0f}%, 기준 {ocr.MIN_CONFIDENCE}%)", kind, round(conf, 1))
    return Extracted(text, True, kind=kind, ocr_confidence=round(conf, 1))


def extract_text(filename: str, data: bytes) -> Extracted:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext == "txt":
            return Extracted(_from_txt(data), True, kind="txt")
        if ext == "docx":
            return Extracted(_from_docx(data), True, kind="docx")
        if ext == "pdf":
            text, n_pages = _from_pdf(data)
            visible = len("".join(text.split()))  # 공백 제외 글자 수
            if visible < MIN_CHARS_PER_PAGE * n_pages:   # 글자 층이 없는 스캔 PDF → OCR
                return _ocr(lambda: ocr.pdf_pages(data), "pdf-ocr")
            return Extracted(text, True, kind="pdf")
        if ext in IMAGE_EXT:
            from PIL import Image
            return _ocr(lambda: [Image.open(io.BytesIO(data))], "image-ocr")
    except Exception as e:  # 손상된 파일 등도 '확인 불가'로 처리
        return Extracted("", False, f"파일을 읽는 중 오류: {e}", ext)
    return Extracted("", False, f"지원하지 않는 형식(.{ext})", ext)
