"""스캔 문서·이미지의 글자를 읽는 OCR (멘토 피드백 1-2, 2-1).

- 엔진: Tesseract(오픈소스, 한국어 학습 데이터 kor) — 인터넷·GPU 없이 사내 서버 CPU에서 동작 → 폐쇄망 조건 충족
- PDF는 pypdfium2로 페이지를 이미지로 바꾼 뒤 읽는다 (외부 프로그램 불필요)
- 전처리: 흑백 → 잡티 제거(중앙값 필터) → 자동 이진화(Otsu). 스캔 잡음이 있는 시험 문서에서
  전처리 없이는 개인정보 6개 중 3~4개만 읽혔고, 전처리 + 문단 모드(psm 6)로 6개 모두 읽혔다.
- 안전장치: 평균 인식 신뢰도가 낮거나 페이지가 너무 많으면 '읽기 불가'로 돌려 차단(fail-closed)한다.
  잘못 읽은 글자 때문에 개인정보를 놓친 채 통과되는 것을 막기 위해서다.
"""
import shutil

MAX_PAGES = 10          # 무료 서버(메모리 512MB)에서 처리 시간을 감당할 수 있는 페이지 수
DPI = 200               # 시험 결과 200dpi와 300dpi의 인식 결과가 같아 더 빠른 쪽 사용
MIN_CONFIDENCE = 60     # 평균 단어 신뢰도(0~100)가 이보다 낮으면 '읽기 불가'


def available() -> bool:
    """Tesseract와 한국어 데이터가 설치돼 있는지 (없으면 예전처럼 스캔 문서는 차단)."""
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract
        return "kor" in pytesseract.get_languages(config="")
    except Exception:
        return False


def _otsu(hist: list[int]) -> int:
    """밝기 히스토그램에서 글자/배경을 가장 잘 나누는 경계값."""
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w_b, sum_b = 0.0, 127, 0, 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, best_t = between, t
    return best_t


def _prepare(img):
    from PIL import ImageFilter
    g = img.convert("L").filter(ImageFilter.MedianFilter(3))
    t = _otsu(g.histogram())
    return g.point(lambda p: 255 if p > t else 0)


def read_images(images) -> tuple[str, float]:
    """이미지 목록 → (전체 텍스트, 평균 신뢰도). 단어가 하나도 없으면 신뢰도 0."""
    import pytesseract
    texts, confs = [], []
    for img in images:
        img = _prepare(img)
        texts.append(pytesseract.image_to_string(img, lang="kor+eng", config="--psm 6"))
        data = pytesseract.image_to_data(img, lang="kor+eng", config="--psm 6", output_type=pytesseract.Output.DICT)
        confs += [float(c) for c, w in zip(data["conf"], data["text"]) if w.strip() and float(c) >= 0]
    return "\n".join(texts), (sum(confs) / len(confs) if confs else 0.0)


def pdf_pages(data: bytes) -> list:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    if len(pdf) > MAX_PAGES:
        raise ValueError(f"스캔 PDF가 {len(pdf)}쪽으로 OCR 한도({MAX_PAGES}쪽)를 넘음")
    return [page.render(scale=DPI / 72).to_pil() for page in pdf]
