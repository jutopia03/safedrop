"""파일에서 텍스트를 추출한다.

원칙: 내용을 확인할 수 없으면 readable=False 로 돌려준다.
판정 단계에서 readable=False 는 규정 7-1에 따라 모든 수신자에게 차단된다(fail-closed).
"""
import io
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader

# 페이지당 평균 글자 수가 이보다 적으면 "스캔 이미지 PDF"로 본다.
MIN_CHARS_PER_PAGE = 20


@dataclass
class Extracted:
    text: str
    readable: bool
    reason: str = ""      # readable=False 인 이유 (화면·로그 표시용)
    kind: str = ""        # txt / docx / pdf


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
            if visible < MIN_CHARS_PER_PAGE * n_pages:
                return Extracted(text, False, "텍스트가 거의 없는 PDF (스캔 이미지로 추정)", "pdf")
            return Extracted(text, True, kind="pdf")
    except Exception as e:  # 손상된 파일 등도 '확인 불가'로 처리
        return Extracted("", False, f"파일을 읽는 중 오류: {e}", ext)
    return Extracted("", False, f"지원하지 않는 형식(.{ext})", ext)
