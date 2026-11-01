"""조항 검색 품질 측정 (LLM 불필요).

정보 유형 5 x 수신자 유형 4 = 20가지 상황마다, 규칙표가 정한 정답 조항이
검색 상위 1개 / 3개 안에 드는지 센다 (Recall@1, Recall@3).
실행: python scripts/eval_retrieval.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.retrieve import query_for, search  # noqa: E402

rules = json.loads((ROOT / "data" / "company" / "rules.json").read_text(encoding="utf-8"))["rules"]
for mode, use_filter in (("① 키워드 검색만 (BM25)", False), ("② BM25 + 조 제목 태그 필터", True)):
    print(f"\n=== {mode} ===")
    hit1 = hit3 = n = 0
    for cat, by_class in rules.items():
        for rclass, rule in by_class.items():
            top = [cid for cid, _ in search(query_for(cat, rclass), k=3, category=cat if use_filter else None)]
            n += 1
            hit1 += bool(top) and top[0] == rule["clause"]
            hit3 += rule["clause"] in top
            if rule["clause"] not in top:
                print(f"  ✘ {cat:<10} {rclass:<10} 정답 {rule['clause']:<4} 검색 {top}")
    print(f"Recall@1 {hit1}/{n} ({hit1/n:.0%})   Recall@3 {hit3}/{n} ({hit3/n:.0%})")
