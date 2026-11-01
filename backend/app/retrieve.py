"""사내 규정 조항 검색 (S7, RAG의 'R').

- 검색 대상: policy.md 의 조항([3-2] 같은 ID 단위)
- 검색 방식: BM25 (단어 빈도·희소성 기반 키워드 검색). 한국어 형태소 분석기 없이도 동작하도록
  글자 2-gram 으로 쪼개서 비교한다. 조항이 수십 개 규모라 임베딩 없이도 충분하고, 결과가 결정적이다.
- 메타데이터 필터: 각 조항이 속한 조의 제목(예: "제5조 (연락처정보의 전송)")을 태그로 써서,
  탐지된 정보 유형에 해당하는 조 안에서만 검색할 수 있다. (측정 결과: 필터 없음 Recall@3 90% → 필터 100%)
- 검색어는 LLM이 만들지 않는다. 탐지 결과(정보 유형)와 수신자 유형에서 정해진 문구로 만든다.
  → 검색어가 흔들려 엉뚱한 조항이 나오는 문제(멘토 피드백)를 줄인다.
"""
import math
import re
from collections import Counter
from functools import lru_cache

from .policy import DATA, clauses

# 정보 유형 → 조 제목에 들어 있는 이름 (메타데이터 필터용)
CATEGORY_LABEL = {
    "UNIQUE_ID": "고유식별정보", "FINANCIAL": "금융정보", "CONTACT": "연락처정보",
    "SENSITIVE": "민감정보", "UNREADABLE": "내용 확인이 불가능한",
}

CATEGORY_TERMS = {
    "UNIQUE_ID": "고유식별정보가 포함된 파일",
    "FINANCIAL": "금융정보가 포함된 파일",
    "CONTACT": "연락처정보가 포함된 파일",
    "SENSITIVE": "민감정보가 포함된 파일",
    "UNREADABLE": "내용을 확인할 수 없는 파일 스캔 이미지",
}
CLASS_TERMS = {
    "PRIVILEGED": "개인정보취급자에게 원본으로 전송",
    "SAME_DEPT": "같은 부서 임직원 마스킹한 사본",
    "INTERNAL": "다른 부서 임직원 개인정보취급자가 아닌 임직원",
    "EXTERNAL": "외부 수신자에게 전송할 수 없다",
}


def _tokens(text: str) -> list[str]:
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", text)
    return [s[i:i + 2] for i in range(len(s) - 1)]


@lru_cache
def headings() -> dict[str, str]:
    """조항ID → 그 조항이 속한 조의 제목. 예: '5-2' → '제5조 (연락처정보의 전송)'"""
    out, current = {}, ""
    for line in (DATA / "policy.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
        m = re.match(r"^\[(\d+-\d+)\]", line)
        if m:
            out[m.group(1)] = current
    return out


@lru_cache
def _index():
    docs = {cid: Counter(_tokens(t)) for cid, t in clauses().items()}
    n = len(docs)
    df = Counter(tok for c in docs.values() for tok in c)
    idf = {tok: math.log(1 + (n - d + 0.5) / (d + 0.5)) for tok, d in df.items()}
    avg = sum(sum(c.values()) for c in docs.values()) / n
    return docs, idf, avg


def search(query: str, k: int = 3, category: str | None = None) -> list[tuple[str, float]]:
    """BM25 점수 상위 k개 조항 (조항ID, 점수). category 를 주면 해당 정보 유형의 조 안에서만 찾는다."""
    docs, idf, avg = _index()
    if category:
        label = CATEGORY_LABEL[category]
        filtered = {c: d for c, d in docs.items() if label in headings().get(c, "")}
        docs = filtered or docs
    q = Counter(_tokens(query))
    k1, b = 1.5, 0.75
    scores = {}
    for cid, tf in docs.items():
        length = sum(tf.values())
        s = 0.0
        for tok in q:
            if tok in tf:
                f = tf[tok]
                s += idf[tok] * f * (k1 + 1) / (f + k1 * (1 - b + b * length / avg))
        scores[cid] = s
    return sorted(scores.items(), key=lambda x: -x[1])[:k]


def query_for(category: str, rclass: str) -> str:
    return f"{CATEGORY_TERMS[category]} {CLASS_TERMS[rclass]}"
