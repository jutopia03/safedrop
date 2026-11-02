# 로컬 LLM 측정: qwen3:14b

| 항목 | 값 |
|---|---|
| 측정 시각 | 2026-11-02 20:21 |
| GPU | NVIDIA GeForce RTX 4080 SUPER, 16376 MiB |
| 측정 전 GPU 메모리 사용 | 785 MiB |
| 측정 중 GPU 메모리 최고 | 10309 MiB |
| 모델 사용 메모리 (최고 − 측정 전) | 9524 MiB |
| 모델 배치 (ollama ps) | `qwen3:14b    bdbd181c33f2    9.7 GB    100% GPU     4096       llamacpp    4 minutes from now` |
| 모델 (ollama list) | `qwen3:14b         bdbd181c33f2    9.3 GB    3 hours ago    ` |
| OS / Python | Windows-10-10.0.19045-SP0 / 3.14.5 |

## 민감정보 판단 정확도 (`eval_sensitive.py`, 123.7초)

```
문장 파일 1개, 문장 20개
  [놓침] s02: 물류팀 강반장님은 신장이 안 좋아서 주 3회 투석받느라 야근에서 빠지신대요.
  [놓침] s07: 품질팀 송대리가 이번 투표에서 야당 후보를 찍었다고 점심시간에 얘기하더라고요.
  [오탐] s17: 홍보팀 문과장님은 이번 주 병가 중이라 복귀는 다음 주 월요일입니다.
  [놓침] s19: 법무팀 도팀장이 국회의원 후보 후원 행사에 참석한 사진이 사내 게시판에 올라왔어요.

모델: qwen3:14b / 문장 20개 / 123.6초
정확도 80% | 재현율 75% | 정밀도 90%
놓친 민감 문장 중 '후보 탈락'(주제 단어 없음): 1개
비교 기준(v0 정규식): 민감정보 재현율 0%
```

## AI 설명 인용 검증 (`eval_explain.py`, 100.9초)

```
✘ CONTACT    INTERNAL   → ['AI 설명 누락']
  ✘ CONTACT    EXTERNAL   → ['AI 설명 누락']
  ✘ SENSITIVE  PRIVILEGED → ['AI 설명 누락']
  ✘ SENSITIVE  SAME_DEPT  → ['AI 설명 누락']
  ✘ SENSITIVE  EXTERNAL   → ['인용 문구가 원문과 다름(6-3: "다른 부서 임직원 및 외부 수신자에게는 민감정보가 포함된 파일을 전송할 ")']
  ✘ UNREADABLE PRIVILEGED → ['인용 문구가 원문과 다름(7-1: "내용 확인 불가 파일은 전송이 금지됩니다.")']
  ✘ UNREADABLE SAME_DEPT  → ['인용 문구가 원문과 다름(7-1: "내용 확인 불가 파일은 전송이 금지됩니다.")']
  ✘ UNREADABLE INTERNAL   → ['인용 문구가 원문과 다름(7-1: "내용 확인 불가 파일은 전송이 금지됩니다.")']
  ✘ UNREADABLE EXTERNAL   → ['인용 문구가 원문과 다름(7-1: "내용 확인 불가 파일은 전송이 금지됩니다.")']

설명 모델 qwen3:14b / 20건 / 100.8초
인용 검증 통과(AI 설명 채택) 11/20 (55%) · 나머지는 템플릿 설명으로 대체
```
