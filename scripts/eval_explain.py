"""v2 설명 생성 품질 측정 (LLM 필요).

20가지 상황(정보 유형 5 x 수신자 유형 4)을 만들어 AI 설명을 받고,
인용 검증(검색된 조항만 인용 / 필수 조항 포함 / 원문 일치 / 조치 언급)을 통과한 비율을 센다.
실패한 경우에도 사용자에게는 템플릿 설명이 나가므로 '틀린 설명이 노출된 비율'은 0%다.
실행: python scripts/eval_explain.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import llm                    # noqa: E402
from backend.app.explain import explain        # noqa: E402
from backend.app.policy import clauses         # noqa: E402

if not llm.enabled():
    sys.exit("OPENAI_API_KEY 가 설정되지 않았습니다 (.env 확인)")
rules = json.loads((ROOT / "data" / "company" / "rules.json").read_text(encoding="utf-8"))["rules"]
decisions = []
for i, (cat, by_class) in enumerate(rules.items()):
    for j, (rclass, rule) in enumerate(by_class.items()):
        decisions.append({
            "recipient": {"id": f"t{i}{j}", "name": f"테스트{i}{j}", "dept": "-", "title": "-"},
            "recipient_class": rclass, "action": rule["action"], "mask_categories": [],
            "reasons": [{"category": cat, "count": 1, "action": rule["action"], "clause": rule["clause"],
                         "clause_text": clauses()[rule["clause"]]}],
        })
t0 = time.time()
ok = 0
for b in range(0, len(decisions), 5):          # 5명씩 묶어 호출 (실제 서비스와 같은 방식)
    batch = decisions[b:b + 5]
    explain(batch)
    for d in batch:
        e = d["explanation"]
        r = d["reasons"][0]
        if e["source"] == "ai":
            ok += 1
        else:
            print(f"  ✘ {r['category']:<10} {d['recipient_class']:<10} → {e['problems']}")
print(f"\n모델 {llm.model_name()} / {len(decisions)}건 / {time.time() - t0:.1f}초")
print(f"인용 검증 통과(AI 설명 채택) {ok}/{len(decisions)} ({ok/len(decisions):.0%}) · 나머지는 템플릿 설명으로 대체")
