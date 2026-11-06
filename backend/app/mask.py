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
    if typ in ("HEALTH", "BELIEF", "POLITICS", "UNION", "PRIVATE"):
        return "[민감정보 가림]"            # 문맥형 민감정보는 문장 전체를 가린다
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
    # 시작 위치 순, 같은 위치면 긴 것(문장 단위 민감정보) 먼저 → 이미 가린 구간 안의 항목은 건너뜀
    for e in sorted(entities, key=lambda x: (x.start, -x.end)):
        if e.category not in categories or e.start < last:
            continue
        out.append(text[last:e.start])
        out.append(mask_value(e.type, e.text))
        last = e.end
    out.append(text[last:])
    return "".join(out)


SEVERITY = {"BLOCK": 0, "MASK": 1, "ALLOW": 2}


def cause_snippets(text: str, entities: list, decision: dict, ctx: int = 30, limit: int = 30) -> list[dict]:
    """차단·마스킹의 원인이 된 부분을 원문에서 찾아 앞뒤 문맥과 함께 돌려준다 (사용자 테스트 피드백 반영).

    '지운 파일로 다시 검사하세요'라는 안내만으로는 어디를 지워야 할지 알 수 없다는 의견에 따라,
    수신자별로 허용되지 않은 정보가 문서의 어느 위치에 있는지 보여준다. 발신자 본인 파일이므로 원문을 보여주되,
    서버 캐시에는 남기지 않고 응답에만 담는다.
    """
    rule = {r["category"]: (r["action"], r["clause"]) for r in decision["reasons"]}
    out = []
    for e in entities:
        action, clause = rule.get(e.category, ("ALLOW", ""))
        if action == "ALLOW":
            continue
        line_start = text.rfind("\n", 0, e.start) + 1
        line_end = text.find("\n", e.end)
        line_end = len(text) if line_end == -1 else line_end
        before = text[max(line_start, e.start - ctx):e.start]
        after = text[e.end:min(line_end, e.end + ctx)]
        hit = text[e.start:e.end].strip()
        out.append({"category": e.category, "type": e.type, "action": action, "clause": clause,
                    "before": ("…" if e.start - ctx > line_start else "") + before,
                    "hit": hit if len(hit) <= 120 else hit[:117] + "…",
                    "after": after + ("…" if e.end + ctx < line_end else ""), "_pos": e.start})
    out.sort(key=lambda x: (SEVERITY[x["action"]], x["_pos"]))
    for x in out:
        del x["_pos"]
    return out[:limit]
