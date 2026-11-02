"""v2: 수신자별 판정 이유를 사람이 읽기 쉬운 설명으로 만든다 (S7, RAG의 'G' + 인용 검증).

흐름
1. 검색: 수신자별로 (정보 유형 × 수신자 유형) 검색어를 만들어 관련 조항을 찾는다 (retrieve.py)
2. 생성: 검색된 조항만 근거로 주고, LLM이 2문장 설명(결과+결정 이유, 대안)을 쓴다 (수신자 전체를 1회 호출로).
   대안은 규정이 허용하는 것만 코드가 미리 정해 주고, 조항 원문은 본문이 아닌 citations에만 넣게 한다.
3. 검증: 코드로 확인 → 하나라도 틀리면 기본(템플릿) 설명으로 대체
   ① 인용한 조항 ID가 검색 결과 안에 있는가   ② 규칙표가 정한 조항을 모두 인용했는가
   ③ 인용 문구가 조항 원문에 글자 그대로 있는가   ④ 설명에 실제 조치(허용/마스킹/차단)가 드러나는가
   ⑤ 200자 이내이고 조항 문장을 본문에 그대로 나열하지 않았는가 (읽기 쉬움)

판정은 규칙표가 이미 끝냈다. 이 단계가 실패해도 판정은 바뀌지 않고, 설명만 기본 문장으로 바뀐다.
"""
import re

from . import llm
from .policy import clauses
from .retrieve import query_for, search

ACTION_WORDS = {"ALLOW": ("원본", "허용"), "MASK": ("마스킹", "가린"), "BLOCK": ("차단", "보낼 수 없", "전송할 수 없")}
ACTION_KO = {"ALLOW": "원본 그대로 전송", "MASK": "마스킹한 사본으로 전송", "BLOCK": "전송 차단"}
CLASS_KO = {"PRIVILEGED": "개인정보취급자", "SAME_DEPT": "같은 부서 임직원", "INTERNAL": "다른 부서 임직원",
            "EXTERNAL": "외부 수신자"}
CAT_KO = {"UNIQUE_ID": "고유식별정보", "FINANCIAL": "금융정보", "CONTACT": "연락처정보",
          "SENSITIVE": "민감정보", "UNREADABLE": "내용 확인 불가 파일"}

SYSTEM = """너는 회사 정보보호 담당자다. 직원이 파일을 보내려 할 때, 수신자별 처리 결과를 직원이 한눈에 이해하도록 설명한다.
규칙:
- 처리 결과(조치)는 이미 정해져 있다. 바꾸거나 다르게 말하지 않는다.
- text는 **2문장, 150자 이내**, 존댓말.
  1문장: 처리 결과 + '결정 이유'(결과를 가장 엄격하게 만든 정보)를 쉬운 말로. 예) "공황장애 진단 등 건강 정보가 있어 다른 부서인 길하람님에게는 전송이 차단됩니다(규정 6-3)."
  2문장: 차단·마스킹이면 직원이 할 수 있는 일. '제안 가능한 대안'에 있는 것만 쓴다. 허용이면 짧은 확인 문장.
- **조항 문장을 text에 옮겨 적지 않는다.** 조항은 번호만 괄호로 쓴다. 조항 원문은 citations에만 넣는다.
- 아직 보내기 전 '검사 결과'이므로 "전송됩니다/차단됩니다"처럼 쓰고, "전송했습니다"처럼 끝난 일로 쓰지 않는다.
- citations: '필수 인용 조항'을 모두, '검색된 조항' 중에서만, 조항 원문에서 글자 그대로 복사해 넣는다.
반드시 아래 JSON 하나로만 답한다:
{"explanations":[{"rid":"u01","text":"설명 2문장","citations":[{"id":"6-3","quote":"조항 원문 일부"}]}]}"""

MAX_TEXT = 200   # 설명 길이 상한 (조항 나열 방지)


def _decisive(d: dict) -> list[dict]:
    """최종 조치를 결정한 사유(가장 엄격한 조치와 같은 사유들)."""
    return [r for r in d["reasons"] if r["action"] == d["action"]]


def _alternatives(d: dict) -> str:
    """규정이 허용하는 범위의 대안 (규칙으로 정함 — LLM이 규정에 없는 방법을 지어내지 않게)."""
    if d["action"] == "ALLOW":
        return ""
    cats = [r["category"] for r in _decisive(d)]
    if d["action"] == "BLOCK":
        if "UNREADABLE" in cats:
            return "글자를 읽을 수 있는 원본 문서나 선명한 스캔으로 다시 보내거나, 정보보호팀에 검토를 요청하세요(7-1)."
        names = "·".join(CAT_KO[c] for c in cats)
        return f"{names}를 지운 파일로 다시 검사하면 보낼 수 있습니다."
    masked = "·".join(CAT_KO[c] for c in d.get("mask_categories") or cats)
    return f"{masked}만 가린 사본이 전송되며, 나머지 내용은 그대로 전달됩니다."


def _template(d: dict) -> str:
    """LLM 없이 만드는 기본 설명 (항상 정확, 2문장)."""
    who = f"{d['recipient']['name']}님({CLASS_KO[d['recipient_class']]})"
    if not d["reasons"]:
        return f"탐지된 개인정보가 없어 {who}에게 원본 그대로 전송됩니다."
    dec = _decisive(d)
    why = "·".join(CAT_KO[r["category"]] for r in dec)
    ids = ", ".join(sorted({r["clause"] for r in dec}))
    head = {"ALLOW": f"{why}가 있지만 {who}에게는 규정상 원본 그대로 전송됩니다(규정 {ids}).",
            "MASK": f"{why} 때문에 {who}에게는 마스킹한 사본으로 전송됩니다(규정 {ids}).",
            "BLOCK": f"{why} 때문에 {who}에게는 전송이 차단됩니다(규정 {ids})."}[d["action"]]
    alt = _alternatives(d)
    return head + (" " + alt if alt else "")


def _retrieved(d: dict) -> list[str]:
    ids = []
    for r in d["reasons"]:
        for cid, _ in search(query_for(r["category"], d["recipient_class"]), k=3, category=r["category"]):
            if cid not in ids:
                ids.append(cid)
    return ids


def _norm(s: str) -> str:
    """인용 비교용: [조항ID] 머리표, 공백, 문장부호를 지우고 비교한다. (표기 차이는 허용, 단어가 바뀌면 불일치)"""
    s = re.sub(r"\[\d+-\d+\]", "", s)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s)


def verify(d: dict, retrieved: list[str], exp: dict) -> list[str]:
    """검증 실패 사유 목록 (비어 있으면 통과)."""
    problems = []
    text = (exp.get("text") or "").strip()
    cites = exp.get("citations") or []
    cited_ids = {c.get("id") for c in cites}
    if not text:
        problems.append("설명 없음")
    for c in cites:
        cid, quote = c.get("id"), (c.get("quote") or "").strip()
        if cid not in retrieved:
            problems.append(f"검색되지 않은 조항 인용({cid})")
        elif not _norm(quote) or _norm(quote) not in _norm(clauses().get(cid, "")):
            problems.append(f"인용 문구가 원문과 다름({cid}: \"{quote[:40]}\")")
    required = {r["clause"] for r in d["reasons"]}
    if not required <= cited_ids:
        problems.append(f"필수 조항 누락({', '.join(sorted(required - cited_ids))})")
    if not any(w in text for w in ACTION_WORDS[d["action"]]):
        problems.append("설명에 실제 조치가 드러나지 않음")
    if len(text) > MAX_TEXT:
        problems.append(f"설명이 너무 김({len(text)}자 > {MAX_TEXT}자)")
    pasted = [cid for cid in retrieved if len(_norm(clauses().get(cid, ""))) >= 15 and _norm(clauses()[cid]) in _norm(text)]
    if pasted:
        problems.append(f"조항 문장을 설명에 그대로 나열({', '.join(pasted)})")
    return problems


def explain(decisions: list[dict], ask=None, use_llm: bool = True) -> None:
    """decisions 각각에 'explanation' 필드를 채운다. ask: 테스트용 LLM 대체 함수(system, user → dict)."""
    retrieved = {d["recipient"]["id"]: _retrieved(d) for d in decisions}
    for d in decisions:
        d["explanation"] = {"text": _template(d), "source": "template", "retrieved": retrieved[d["recipient"]["id"]],
                            "problems": []}
    targets = [d for d in decisions if d["reasons"]]
    if not targets or not use_llm or (ask is None and not llm.enabled()):
        return
    blocks = []
    for d in targets:
        rid = d["recipient"]["id"]
        found = ", ".join(f"{CAT_KO[r['category']]} {r.get('count', 1)}건" for r in d["reasons"])
        decisive = ", ".join(f"{CAT_KO[r['category']]} → {ACTION_KO[r['action']]} ({r['clause']})" for r in _decisive(d))
        docs = "\n".join(f"    [{cid}] {clauses()[cid]}" for cid in retrieved[rid])
        blocks.append(f"- rid={rid} / {d['recipient']['name']} ({CLASS_KO[d['recipient_class']]})\n"
                      f"  파일 속 정보: {found}\n  처리 결과: {ACTION_KO[d['action']]}\n"
                      f"  결정 이유: {decisive}\n  제안 가능한 대안: {_alternatives(d) or '(허용이므로 없음)'}\n"
                      f"  필수 인용 조항: {', '.join(sorted({r['clause'] for r in d['reasons']}))}\n  검색된 조항:\n{docs}")
    try:
        data = ask(SYSTEM, "\n".join(blocks)) if ask else llm.complete_json(SYSTEM, "\n".join(blocks), max_tokens=6000, model=llm.explain_model())
    except llm.LLMError as e:
        for d in targets:
            d["explanation"]["problems"] = [f"AI 설명 실패: {e}"]
        return
    by_rid = {str(x.get("rid")): x for x in data.get("explanations", [])}
    for d in targets:
        rid = d["recipient"]["id"]
        exp = by_rid.get(rid)
        if not exp:
            d["explanation"]["problems"] = ["AI 설명 누락"]
            continue
        problems = verify(d, retrieved[rid], exp)
        if problems:
            d["explanation"]["problems"] = problems          # 템플릿 설명 유지
        else:
            d["explanation"].update(text=exp["text"].strip(), source="ai",
                                    citations=[c["id"] for c in exp["citations"]])
