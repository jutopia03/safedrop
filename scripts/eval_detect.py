"""테스트 문서 세트로 탐지 성능을 측정한다. (버전별 비교용)

실행: python scripts/eval_detect.py            (결과를 화면에)
      python scripts/eval_detect.py v0         (결과를 docs/eval/detect_v0.md 에도 저장 — 버전별 비교 기록)
- 재현율(recall): 정답 개인정보 중 몇 개를 찾았나  → 낮으면 '놓침(미탐)'이 많다
- 정밀도(precision): 찾은 것 중 몇 개가 진짜인가 → 낮으면 '잘못 잡음(오탐)'이 많다
비교는 (세부유형, 공백 제거한 글자) 기준. RRN과 FRN은 같은 것으로 본다.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.detect import detect          # noqa: E402
from backend.app.extract import extract_text   # noqa: E402

TESTSET = ROOT / "data" / "testset"


def key(typ: str, text: str):
    typ = "RRN" if typ in ("RRN", "FRN") else typ
    return typ, re.sub(r"\s", "", text)


def main():
    out = []
    import builtins
    _print = builtins.print

    def print(*a, **k):          # noqa: A001 — 화면 출력과 동시에 기록용으로 모은다
        _print(*a, **k)
        out.append(" ".join(str(x) for x in a))

    # labels.json(예시) + docs/labels_<이름>.json(팀원별 정답 파일 → 각자 PR이 서로 충돌하지 않음)을 합친다
    # (정답 파일을 data/testset/ 바로 아래에 둔 경우도 함께 읽는다)
    files = ([TESTSET / "labels.json"] + sorted(TESTSET.glob("labels_*.json"))
             + sorted((TESTSET / "docs").glob("labels_*.json")))
    labels = []
    for f in files:
        labels += json.loads(f.read_text(encoding="utf-8"))
    print(f"정답 파일 {len(files)}개, 문서 {len(labels)}개")
    tp = Counter(); fp = Counter(); fn = Counter()
    unreadable = []
    for item in labels:
        path = TESTSET / "docs" / item["file"]
        if not path.exists():
            print(f"[건너뜀] 파일 없음: {item['file']}")
            continue
        ex = extract_text(path.name, path.read_bytes())
        if not ex.readable:
            unreadable.append(item["file"])
            # 읽을 수 없는 파일은 차단되므로, 정답에 개인정보가 있어도 '유출'은 아님 → 집계에서 제외
            continue
        gold = Counter(key(e["type"], e["text"]) for e in item["entities"] if e["category"] != "SENSITIVE")
        pred = Counter(key(e.type, e.text) for e in detect(ex.text))
        for k in gold | pred:
            hit = min(gold[k], pred[k])
            tp[k[0]] += hit
            fn[k[0]] += gold[k] - hit
            fp[k[0]] += pred[k] - hit
            for _ in range(gold[k] - hit):
                print(f"  [놓침] {item['file']}: {k[0]} {k[1]}")
            for _ in range(pred[k] - hit):
                print(f"  [오탐] {item['file']}: {k[0]} {k[1]}")

    print("\n유형      정답  찾음  맞음  재현율  정밀도")
    types = sorted(set(tp) | set(fp) | set(fn))
    for t in types + ["전체"]:
        T = sum(tp.values()) if t == "전체" else tp[t]
        P = T + (sum(fp.values()) if t == "전체" else fp[t])
        G = T + (sum(fn.values()) if t == "전체" else fn[t])
        rec = f"{T/G:.0%}" if G else "-"
        pre = f"{T/P:.0%}" if P else "-"
        print(f"{t:<9}{G:>5}{P:>6}{T:>6}{rec:>8}{pre:>8}")
    print(f"\n검사 불가로 차단된 문서: {len(unreadable)}개 {unreadable}")
    print("※ 민감정보(SENSITIVE)는 정규식 대상이 아니라 제외 (v1 LLM 평가에서 측정)")
    if len(sys.argv) > 1:
        import datetime
        dest = ROOT / "docs" / "eval" / f"detect_{sys.argv[1]}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        dest.write_text(f"# 정규식 탐지 측정: {sys.argv[1]} ({stamp})\n\n```\n" + "\n".join(out) + "\n```\n", encoding="utf-8")
        _print(f"\n저장: {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
