# 정규식 탐지 측정: v0.1 (2026-11-02 18:30)

```
정답 파일 2개, 문서 21개
  [오탐] doc_최시원_10_구독환불_처리내역서.txt: ACCOUNT 391-910012-34507
  [놓침] doc_최시원_13_사진_재직증명서.png: EMAIL hyun.namgung88@mail.example
  [오탐] doc_최시원_13_사진_재직증명서.png: EMAIL hyun.namgungs8@mail.example
  [놓침] doc_최시원_15_경조사비_신청서.docx: PHONE 031-704-2286
  [놓침] doc_최시원_18_스캔PDF_입사지원서.pdf: PASSPORT M71839264

유형      정답  찾음  맞음  재현율  정밀도
ACCOUNT      9    10     9    100%     90%
CARD         3     3     3    100%    100%
DRIVER       1     1     1    100%    100%
EMAIL       16    16    15     94%     94%
PASSPORT     2     1     1     50%    100%
PHONE       24    23    23     96%    100%
RRN          5     5     5    100%    100%
전체          60    59    57     95%     97%

검사 불가로 차단된 문서: 1개 ['doc_최시원_14_흐린스캔_입사서류동의서.png']
※ 민감정보(SENSITIVE)는 정규식 대상이 아니라 제외 (v1 LLM 평가에서 측정)
```
