"""규칙표 기반 수신자별 판정과 마스킹."""
from backend.app.detect import Entity, detect
from backend.app.mask import mask_text
from backend.app.policy import clauses, judge

DOC = "주민등록번호 950312-2345678\n연락처 010-9876-5432\n신한 110-234-567890"


def by_name(decisions):
    return {d["recipient"]["id"]: d for d in decisions}


def test_recipient_classes_and_actions():
    # 영업팀 변시우(u05) → 인사팀 취급자 / 같은 부서 / 다른 부서 / 협력사
    d = by_name(judge(detect(DOC), True, "u05", ["u01", "u06", "u07", "x01"]))
    assert (d["u01"]["recipient_class"], d["u01"]["action"]) == ("PRIVILEGED", "ALLOW")
    assert (d["u06"]["recipient_class"], d["u06"]["action"]) == ("SAME_DEPT", "MASK")
    assert (d["u07"]["recipient_class"], d["u07"]["action"]) == ("INTERNAL", "MASK")
    assert (d["x01"]["recipient_class"], d["x01"]["action"]) == ("EXTERNAL", "BLOCK")


def test_every_reason_has_real_clause_text():
    for d in judge(detect(DOC), True, "u05", ["u01", "u06", "x01"]):
        for r in d["reasons"]:
            assert r["clause"] in clauses() and r["clause_text"] == clauses()[r["clause"]]


def test_unreadable_blocks_everyone():
    for d in judge([], False, "u05", ["u01", "x01"]):
        assert d["action"] == "BLOCK" and d["reasons"][0]["clause"] == "7-1"


def test_mask_only_masked_categories():
    ents = detect(DOC)
    d = by_name(judge(ents, True, "u05", ["u06"]))["u06"]
    out = mask_text(DOC, ents, d["mask_categories"])
    assert "950312-2******" in out and "***-***-**7890" in out
    assert "010-9876-5432" in out            # 사내 직원에게 연락처는 허용 → 가리지 않음


def test_sensitive_sentence_masked_whole():
    text = "길하람 사원 공황장애 진단. 연락처 010-1111-2222"
    s = text.index("길하람"); e = text.index("진단.") + 3
    ents = detect(text) + [Entity("SENSITIVE", "HEALTH", text[s:e], s, e)]
    assert mask_text(text, ents, ["SENSITIVE"]).startswith("[민감정보 가림]")


# ---- 원인 위치 보기 (사용자 테스트 피드백 반영) ----
def test_cause_snippets_show_where_blocked_and_masked():
    from backend.app.mask import cause_snippets
    text = "성명: 도윤슬\n주민등록번호: 950312-2345678\n연락처: 010-9876-5432"
    ents = detect(text)
    ext = judge(ents, True, "u05", ["x01"])[0]                  # 협력사: 주민번호 차단, 연락처 마스킹
    c = cause_snippets(text, ents, ext)
    assert [x["action"] for x in c] == ["BLOCK", "MASK"]           # 차단 원인이 먼저
    assert c[0]["hit"] == "950312-2345678" and c[0]["before"].startswith("주민등록번호") and c[0]["clause"] == "3-3"
    inside = judge(ents, True, "u05", ["u02"])[0]                # 취급자: 모두 허용 → 원인 없음
    assert cause_snippets(text, ents, inside) == []
