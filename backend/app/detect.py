"""정규식 + 검증 로직 기반 개인정보 탐지기 (v0 베이스라인 → v0.1 문맥 보강).

설계 원칙
1. 형식이 정해진 정보만 규칙으로 잡는다. (이름·주소·건강정보 같은 비정형 정보는 v1에서 LLM이 담당)
2. "숫자 모양"만 보지 않고 검증한다: 카드번호 Luhn 검사, 주민번호 생년월일 검사, 주변 키워드 확인.
3. 패턴 사이에 겹침이 생기면 더 구체적인 패턴이 먼저 차지한다. (예: 전화번호가 계좌번호로 잡히지 않게)

v0.1 개선 (팀원 테스트 문서 1차 측정에서 발견한 오탐·미탐 기준, docs/eval/ 참고)
- 주민번호: 같은 줄·표 머리글에 '주민/외국인등록' 키워드가 있거나 체크섬이 맞을 때만. 제조번호·바코드 문맥은 제외
- 이메일: hr@, cx@, press@ 같은 팀 공용 메일은 규정 2-4의 '개인 이메일'이 아니므로 제외
- 카드: Luhn 검사 통과 또는 '카드' 키워드가 붙은 16자리 (법인카드 제외)
- 계좌: '이체 요청ID'처럼 ID·일시(YYYYMMDDhhmmss) 형태인 숫자는 제외
- 여권: 영문 1자 + 숫자 7~8자리(구형 포함), 휴대전화: (010)…, +82-10-… 표기
"""
import re
from dataclasses import dataclass, asdict
from datetime import date

# 숫자 바로 옆에 붙은 경우를 제외하기 위한 경계 (\b는 한글 옆에서 잘 동작하지 않음)
NB = r"(?<![0-9A-Za-z])"
NA = r"(?![0-9A-Za-z])"
SEP = r"[-\s.]?"  # 하이픈·공백·점 구분자 허용


@dataclass
class Entity:
    category: str   # 규칙표 category (UNIQUE_ID / FINANCIAL / CONTACT ...)
    type: str       # 세부 유형 (RRN, CARD ...)
    text: str       # 문서에 적힌 그대로
    start: int
    end: int

    def to_dict(self):
        return asdict(self)


# ---------- 검증 함수 ----------
def _valid_birth(yymmdd: str, gender_digit: str) -> bool:
    """주민·외국인등록번호 앞 6자리가 실제 날짜인지. 7번째 자리로 세기를 판단한다.
    (2020년 10월 이후 발급 번호는 마지막 자리 검증식이 없어 체크섬은 쓰지 않는다.)"""
    century = {"1": 1900, "2": 1900, "5": 1900, "6": 1900,
               "3": 2000, "4": 2000, "7": 2000, "8": 2000,
               "9": 1800, "0": 1800}.get(gender_digit)
    if century is None:
        return False
    try:
        date(century + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
        return True
    except ValueError:
        return False


def _luhn(digits: str) -> bool:
    """카드번호 검증 (Luhn 알고리즘)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _has_keyword(text: str, start: int, keywords: tuple[str, ...], window: int = 25) -> bool:
    """매칭 위치 앞쪽 window 글자 안(같은 줄)에 키워드가 있는지."""
    before = text[max(0, start - window):start].split("\n")[-1]
    return any(k in before for k in keywords)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _rrn_checksum(d: str) -> bool:
    """2020년 10월 이전 발급 주민번호의 마지막 자리 검증식."""
    w = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)
    return (11 - sum(int(a) * b for a, b in zip(d[:12], w)) % 11) % 10 == int(d[12])


RRN_KEYS = ("주민", "외국인", "등록번호", "생년월일", "RRN", "실명번호")
NOT_RRN_KEYS = ("제조", "LOT", "Lot", "lot", "시리얼", "일련번호", "바코드", "EAN", "자산", "주문번호", "송장", "모델")


def _context(text: str, start: int, lines_above: int = 5) -> tuple[str, str]:
    """(같은 줄의 앞부분, 위쪽 몇 줄 = 표 머리글 후보)."""
    head = text[:start]
    same = head.split("\n")[-1]
    above = "\n".join(head.split("\n")[-1 - lines_above:-1])
    return same, above


def _rrn_ok(m, text: str) -> bool:
    same, above = _context(text, m.start())
    if any(k in same for k in RRN_KEYS):
        return True                                   # "주민등록번호: 950312-…"
    if any(k in same or k in above for k in NOT_RRN_KEYS):
        return False                                  # 제조번호(LOT)·바코드 표
    if any(k in above for k in RRN_KEYS):
        return True                                   # 표 머리글에 '주민등록번호'
    return _rrn_checksum(_digits(m.group()))          # 문맥이 없으면 검증식으로 판단


ROLE_MAIL = {"hr", "cx", "cs", "press", "pr", "partners", "partner", "finance", "ga", "privacy", "support", "voice",
             "info", "help", "helpdesk", "admin", "contact", "sales", "marketing", "recruit", "ir", "security",
             "it", "ops", "oncall", "dev", "infra", "pay", "team", "service", "noreply", "no", "reply", "webmaster",
             "office", "center", "biz", "legal", "account", "accounts", "billing"}


def _personal_email(m, text: str) -> bool:
    """팀 공용 메일(hr@, pay-ops@ 등)은 개인 이메일이 아니다. '공용' 문맥도 제외."""
    local = m.group().split("@")[0].lower()
    if all(tok in ROLE_MAIL for tok in re.split(r"[-._+]", local) if tok):
        return False
    same, _ = _context(text, m.start())
    return "공용" not in same[-20:]


def _card_ok(m, text: str) -> bool:
    if "법인" in text[max(0, m.start() - 10):m.start()]:
        return False                                  # 법인카드는 회사 자산이지 개인정보가 아님
    return _luhn(_digits(m.group())) or _has_keyword(text, m.start(), ("카드", "card", "Card", "CARD"), window=30)


def _account_ok(m, text: str) -> bool:
    d = _digits(m.group())
    if not 10 <= len(d) <= 14:
        return False
    near = text[max(0, m.start() - 8):m.start()]
    if any(k in near for k in ("ID", "Id", "id", "요청", "주문", "승인", "접수", "알림", "티켓")):
        return False                                  # "이체 요청ID 20261029160012"
    if len(d) == 14 and re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([01]\d|2[0-3])[0-5]\d[0-5]\d", d):
        return False                                  # 일시(YYYYMMDDhhmmss) 형태
    return _has_keyword(text, m.start(), ("계좌", "은행", "입금", "이체", "국민", "신한", "우리", "하나", "농협",
                                          "기업", "카카오", "토스", "새마을", "우체국", "KB", "IBK", "NH"))


# ---------- 패턴 정의 (위에서부터 우선 적용) ----------
# 각 항목: (category, type, 정규식, 검증함수 또는 None). category=None 은 "개인정보 아님"으로 자리만 차지.
PATTERNS = [
    ("UNIQUE_ID", "RRN_OR_FRN",
     re.compile(NB + r"(\d{6})\s?-?\s?([0-9])(\d{6})" + NA), _rrn_ok),
    ("FINANCIAL", "CARD",
     re.compile(NB + r"\d{4}" + SEP + r"\d{4}" + SEP + r"\d{4}" + SEP + r"\d{4}" + NA),
     _card_ok),
    ("CONTACT", "PHONE",
     re.compile(NB + r"01[016789]" + SEP + r"\d{3,4}" + SEP + r"\d{4}" + NA
                + r"|\(01[016789]\)\s?\d{3,4}" + SEP + r"\d{4}" + NA
                + r"|\+82[-\s]?1[016789]" + SEP + r"\d{3,4}" + SEP + r"\d{4}" + NA), None),
    # 유선전화(회사 대표번호 등)는 개인 연락처가 아니므로 탐지하지 않되, 계좌번호로 오인되지 않게 자리만 차지
    (None, "LANDLINE",
     re.compile(NB + r"0(?:2|[3-6][1-5]|70|80)" + SEP + r"\d{3,4}" + SEP + r"\d{4}" + NA), None),
    ("CONTACT", "EMAIL",
     re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), _personal_email),
    ("UNIQUE_ID", "DRIVER",
     re.compile(NB + r"(?:1[1-9]|2[0-8])-\d{2}-\d{6}-\d{2}" + NA), None),
    ("UNIQUE_ID", "PASSPORT",  # 구형 M12345678·C1234567 / 신형 M123A4567. 일련번호와 헷갈려 '여권' 키워드 필요
     re.compile(NB + r"[A-Z](?:\d{7,8}|\d{3}[A-Z]\d{4})" + NA),
     lambda m, t: _has_keyword(t, m.start(), ("여권", "passport", "Passport", "PASSPORT"), window=12)),
    ("FINANCIAL", "ACCOUNT",  # 은행마다 형식이 달라 '숫자 10~14자리 + 계좌 관련 키워드'로 판단
     re.compile(NB + r"\d{2,6}-\d{2,6}-\d{2,7}(?:-\d{1,3})?" + NA + r"|" + NB + r"\d{10,14}" + NA),
     _account_ok),
]


def detect(text: str) -> list[Entity]:
    taken: list[tuple[int, int]] = []  # 이미 다른 패턴이 차지한 구간
    found: list[Entity] = []

    def overlaps(s, e):
        return any(s < te and ts < e for ts, te in taken)

    for category, typ, rx, validator in PATTERNS:
        for m in rx.finditer(text):
            s, e = m.start(), m.end()
            if overlaps(s, e):
                continue
            if typ == "RRN_OR_FRN":
                birth, g = m.group(1), m.group(2)
                if not _valid_birth(birth, g) or not validator(m, text):
                    continue
                typ_final = "FRN" if g in "5678" else "RRN"
            else:
                typ_final = typ
                if validator and not validator(m, text):
                    continue
            taken.append((s, e))
            if category:
                found.append(Entity(category, typ_final, m.group(), s, e))
    return sorted(found, key=lambda x: x.start)
