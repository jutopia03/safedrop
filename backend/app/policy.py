"""규칙표 기반 수신자별 판정 (S3).

입력: 탐지 결과(Entity 목록), 읽기 가능 여부, 발신자, 수신자 목록
출력: 수신자마다 { 조치(ALLOW/MASK/BLOCK), 근거(유형별 조치·조항), 마스킹할 유형 }

판정 규칙
- 수신자 유형: 외부 > 개인정보취급자 > 같은 부서 > 다른 부서 순으로 결정
- 파일에 여러 유형이 섞여 있으면, 유형별 조치 중 가장 엄격한 것이 그 수신자의 최종 조치 (BLOCK > MASK > ALLOW)
- 최종 조치가 MASK면, 조치가 MASK인 유형만 가린 사본을 보낸다
- LLM은 이 판정에 관여하지 않는다 (결정적·재현 가능한 판정)
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "company"
SEVERITY = {"ALLOW": 0, "MASK": 1, "BLOCK": 2}


@lru_cache
def _rules() -> dict:
    return json.loads((DATA / "rules.json").read_text(encoding="utf-8"))


@lru_cache
def _people() -> dict:
    org = json.loads((DATA / "org.json").read_text(encoding="utf-8"))
    return {p["id"]: p for p in org["people"]}


@lru_cache
def clauses() -> dict[str, str]:
    """policy.md 에서 '[3-2] 문장' 형식을 읽어 {조항ID: 원문} 으로 만든다. (v2 인용 검증에도 사용)"""
    text = (DATA / "policy.md").read_text(encoding="utf-8")
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^\[(\d+-\d+)\]\s*(.+)$", text, re.M)}


def recipient_class(sender: dict, recipient: dict) -> str:
    if recipient["external"]:
        return "EXTERNAL"
    if recipient["privileged"]:
        return "PRIVILEGED"
    if recipient["dept"] == sender["dept"]:
        return "SAME_DEPT"
    return "INTERNAL"


def judge(entities: list, readable: bool, sender_id: str, recipient_ids: list[str]) -> list[dict]:
    people = _people()
    rules = _rules()["rules"]
    sender = people[sender_id]

    # 파일에 들어 있는 정보 유형별 개수
    if not readable:
        found = {"UNREADABLE": 1}
    else:
        found: dict[str, int] = {}
        for e in entities:
            found[e.category] = found.get(e.category, 0) + 1

    results = []
    for rid in recipient_ids:
        if rid == sender_id:
            continue
        rcpt = people[rid]
        rclass = recipient_class(sender, rcpt)
        reasons = []
        for category, count in found.items():
            rule = rules[category][rclass]
            reasons.append({
                "category": category,
                "count": count,
                "action": rule["action"],
                "clause": rule["clause"],
                "clause_text": clauses().get(rule["clause"], ""),
            })
        if reasons:
            final = max((r["action"] for r in reasons), key=SEVERITY.get)
        else:
            final = "ALLOW"  # 탐지된 개인정보 없음
        results.append({
            "recipient": {k: rcpt[k] for k in ("id", "name", "dept", "title")},
            "recipient_class": rclass,
            "action": final,
            "mask_categories": sorted(r["category"] for r in reasons if r["action"] == "MASK") if final == "MASK" else [],
            "reasons": sorted(reasons, key=lambda r: -SEVERITY[r["action"]]),
        })
    return results
