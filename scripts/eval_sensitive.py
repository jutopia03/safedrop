"""v1(LLM) 민감정보 판단 성능 측정. 팀원 C가 만든 data/testset/sensitive.json 을 사용한다.

실행: OPENAI_API_KEY 등을 .env 에 넣고  python scripts/eval_sensitive.py
- 문장 하나를 문서 하나로 보고 '민감정보 있음/없음'을 맞혔는지 센다.
- '후보 탈락'은 주제 단어가 없어 LLM에 아예 보내지 않은 문장(사전 필터의 한계)이다.
- 베이스라인(v0, 정규식)은 민감정보를 전혀 못 잡으므로 재현율 0%와 비교한다.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import llm                                # noqa: E402
from backend.app.sensitive import candidates, detect_sensitive  # noqa: E402


def main():
    base = ROOT / "data" / "testset"
    files = ([base / "sensitive.json"] if (base / "sensitive.json").exists() else []) + sorted((base / "docs").glob("sensitive_*.json"))
    if not files:
        sys.exit("data/testset/docs/sensitive_<이름>.json 문장 세트가 아직 없습니다")
    if not llm.enabled():
        sys.exit("OPENAI_API_KEY 가 설정되지 않았습니다 (.env 확인)")
    items = []
    for f in files:
        items += json.loads(f.read_text(encoding="utf-8"))
    print(f"문장 파일 {len(files)}개, 문장 {len(items)}개")
    tp = fp = fn = tn = dropped = 0
    t0 = time.time()
    for it in items:
        text = it["text"]
        if not candidates(text):
            dropped += it["sensitive"]
        found, info = detect_sensitive(text)
        pred = bool(found)
        if info.get("error"):
            print(f"  [AI 실패→보수 처리] {it['id']}: {info['error']}")
        if pred and it["sensitive"]: tp += 1
        elif pred: fp += 1; print(f"  [오탐] {it['id']}: {text}")
        elif it["sensitive"]: fn += 1; print(f"  [놓침] {it['id']}: {text}")
        else: tn += 1
    n = len(items)
    print(f"\n모델: {llm.model_name()} / 문장 {n}개 / {time.time() - t0:.1f}초")
    print(f"정확도 {(tp + tn) / n:.0%} | 재현율 {tp / max(tp + fn, 1):.0%} | 정밀도 {tp / max(tp + fp, 1):.0%}")
    print(f"놓친 민감 문장 중 '후보 탈락'(주제 단어 없음): {dropped}개")
    print("비교 기준(v0 정규식): 민감정보 재현율 0%")


if __name__ == "__main__":
    main()
