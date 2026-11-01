"""v2: 수신자별 판정 이유를 사람이 읽기 쉬운 설명으로 만든다 (S7, RAG의 'G' + 인용 검증).

흐름
1. 검색: 수신자별로 (정보 유형 × 수신자 유형) 검색어를 만들어 관련 조항을 찾는다 (retrieve.py)
2. 생성: 검색된 조항만 근거로 주고, LLM이 2~3문장 설명 + 가능한 대안을 쓴다 (수신자 전체를 1회 호출로)
3. 검증: 코드로 확인 → 하나라도 틀리면 기본(템플릿) 설명으로 대체
   ① 인용한 조항 ID가 검색 결과 안에 있는가   ② 규칙표가 정한 조항을 모두 인용했는가
   ③ 인용 문구가 조항 원문에 글자 그대로 있는가   ④ 설명에 실제 조치(허용/마스킹/차단)가 드러나는가

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

SYSTEM = """너는 회사 정보보호 담당자다. 직원이 파일을 보내려 할 때, 수신자별 처리 결과를 직원에게 설명한다.
규칙:
- 처리 결과(조치)는 이미 정해져 있다. 바꾸거나 다르게 말하지 않는다.
- 근거는 반드시 '검색된 조항' 중에서만 인용하고, 인용 문구는 조항 원문에서 글자 그대로 복사한다.
- '필수 인용 조항'은 반드시 인용한다.
- 설명은 2~3문장, 존댓말. 아직 보내기 전 '검사 결과'이므로 "전송됩니다/차단됩니다"처럼 쓰고, "전송했습니다/차단했습니다"처럼 이미 끝난 일로 쓰지 않는다.
- 차단·마스킹이면 직원이 할 수 있는 대안을 한 문장 덧붙이되, 검색된 조항이 허용하는 방법만 제안한다.
  예) 민감정보·고유식별정보 때문에 차단이면 "해당 내용을 삭제한 파일로 다시 보내기" 또는 "개인정보취급자를 통해 요청하기".
  규정상 그 수신자에게 금지된 방식(예: 다른 부서에 민감정보 마스킹본 전송)을 제안하지 않는다.
반드시 아래 JSON 하나로만 답한다:
{"explanations":[{"rid":"u01","text":"설명","citations":[{"id":"3-3","quote":"조항 원문 일부"}]}]}"""


def _template(d: dict) -> str:
    """LLM 없이 만드는 기본 설명 (항상 정확)."""
    parts = [f"{CAT_KO[r['category']]}: {ACTION_KO[r['action']]} [{r['clause']}] {r['clause_text']}" for r in d["reasons"]]
    head = f"{d['recipient']['name']}님은 {CLASS_KO[d['recipient_class']]}이므로 최종 결과는 '{ACTION_KO[d['action']]}'입니다."
    return head + (" " + " / ".join(parts) if parts else " 탐지된 개인정보가 없습니다.")


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
        docs = "\n".join(f"    [{cid}] {clauses()[cid]}" for cid in retrieved[rid])
        blocks.append(f"- rid={rid} / {d['recipient']['name']} ({CLASS_KO[d['recipient_class']]})\n"
                      f"  파일 속 정보: {found}\n  처리 결과: {ACTION_KO[d['action']]}\n"
                      f"  필수 인용 조항: {', '.join(sorted({r['clause'] for r in d['reasons']}))}\n  검색된 조항:\n{docs}")
    try:
        data = ask(SYSTEM, "\n".join(blocks)) if ask else llm.complete_json(SYSTEM, "\n".join(blocks), max_tokens=6000)
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
