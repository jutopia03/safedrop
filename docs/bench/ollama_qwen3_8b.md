# 로컬 LLM 측정: qwen3:8b

| 항목 | 값 |
|---|---|
| 측정 시각 | 2026-11-02 20:59 |
| GPU | NVIDIA GeForce RTX 4080 SUPER, 16376 MiB |
| 측정 전 GPU 메모리 사용 | 891 MiB |
| 측정 중 GPU 메모리 최고 | 6521 MiB |
| 모델 사용 메모리 (최고 − 측정 전) | 5630 MiB |
| 모델 배치 (ollama ps) | `qwen3:8b    500a1f067a9f    5.6 GB    100% GPU     4096       llamacpp    4 minutes from now` |
| 모델 (ollama list) | `qwen3:8b          500a1f067a9f    5.2 GB    3 hours ago` |
| OS / Python | Windows-10-10.0.19045-SP0 / 3.14.5 |

## 민감정보 판단 정확도 (`eval_sensitive.py`, 80.8초)

```
문장 파일 1개, 문장 20개
  [오탐] s16: 경영지원팀 김대리 요즘 점심도 거르고 많이 힘들어 보여요.
  [오탐] s17: 홍보팀 문과장님은 이번 주 병가 중이라 복귀는 다음 주 월요일입니다.

모델: qwen3:8b / 문장 20개 / 80.6초
정확도 90% | 재현율 100% | 정밀도 86%
놓친 민감 문장 중 '후보 탈락'(주제 단어 없음): 0개
비교 기준(v0 정규식): 민감정보 재현율 0%
```

## AI 설명 인용 검증 (`eval_explain.py`, 38.6초)

```
✘ UNIQUE_ID  PRIVILEGED → ["AI 설명 실패: JSON 해석 실패: Expecting ',' delimiter: line 1 column 179 (char 178)"]
  ✘ UNIQUE_ID  SAME_DEPT  → ["AI 설명 실패: JSON 해석 실패: Expecting ',' delimiter: line 1 column 179 (char 178)"]
  ✘ UNIQUE_ID  INTERNAL   → ["AI 설명 실패: JSON 해석 실패: Expecting ',' delimiter: line 1 column 179 (char 178)"]
  ✘ UNIQUE_ID  EXTERNAL   → ["AI 설명 실패: JSON 해석 실패: Expecting ',' delimiter: line 1 column 179 (char 178)"]
  ✘ FINANCIAL  PRIVILEGED → ["AI 설명 실패: JSON 해석 실패: Expecting ',' delimiter: line 1 column 179 (char 178)"]

설명 모델 qwen3:8b / 20건 / 38.5초
인용 검증 통과(AI 설명 채택) 15/20 (75%) · 나머지는 템플릿 설명으로 대체
```
