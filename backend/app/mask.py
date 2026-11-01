"""탐지 위치를 이용해 개인정보를 가린 사본을 만든다 (S3).

MVP 한계: 원본 형식(PDF·DOCX)을 유지하지 않고 '마스킹된 텍스트 사본(.txt)'을 만든다.
알아볼 수 있을 만큼만 남기고(앞·뒤 일부) 나머지 글자·숫자를 *로 바꾼다.
"""


def _star(s: str, keep_head: int, keep_tail: int) -> str:
    """구분자(-, 공백, @ 등)는 남기고 영숫자만 가린다."""
    idx = [i for i, c in enumerate(s) if c.isalnum()]
    hide = set(idx[keep_head: len(idx) - keep_tail if keep_tail else None])
    return "".join("*" if i in hide else c for i, c in enumerate(s))


def mask_value(typ: str, text: str) -> str:
    if typ in ("RRN", "FRN"):
        return _star(text, 7, 0)          # 900101-1****** (생년월일 + 성별자리만)
    if typ == "PHONE":
        return _star(text, 3, 4)          # 010-****-5678
    if typ == "EMAIL":
        local, _, domain = text.partition("@")
        return _star(local, 1, 0) + "@" + domain   # m*****@example.com
    if typ == "CARD":
        return _star(text, 4, 4)          # 4111-****-****-1111
    if typ == "ACCOUNT":
        return _star(text, 0, 4)          # ***-***-**7890
    return _star(text, 1, 0)              # 여권·면허 등: 첫 글자만


def mask_text(text: str, entities: list, categories: list[str]) -> str:
    out, last = [], 0
    for e in sorted(entities, key=lambda x: x.start):
        if e.category not in categories:
            continue
        out.append(text[last:e.start])
        out.append(mask_value(e.type, e.text))
        last = e.end
    out.append(text[last:])
    return "".join(out)
