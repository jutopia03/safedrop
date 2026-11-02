# 정규식 탐지 측정: v0 (2026-11-02 18:28)

```
정답 파일 2개, 문서 21개
  [오탐] doc_최시원_01_인사기록카드.txt: EMAIL hr@codev.example
  [오탐] doc_최시원_02_CS티켓_가맹점정산지연.txt: ACCOUNT 20261029160012
  [오탐] doc_최시원_02_CS티켓_가맹점정산지연.txt: EMAIL cx@codev.example
  [놓침] doc_최시원_03_장애보고서_카드승인오류.txt: CARD 9410112345876620
  [오탐] doc_최시원_03_장애보고서_카드승인오류.txt: EMAIL pay-ops@codev.example
  [놓침] doc_최시원_04_외국인개발자_근로계약서.txt: PASSPORT C4829175
  [오탐] doc_최시원_07_인사팀_대외비메모.txt: EMAIL voice@codev.example
  [오탐] doc_최시원_08_보도자료_정산서비스출시.txt: EMAIL press@codev.example
  [오탐] doc_최시원_08_보도자료_정산서비스출시.txt: EMAIL partners@codev.example
  [놓침] doc_최시원_09_프리랜서_용역계약_대금지급.txt: PHONE +82-10-5527-1093
  [놓침] doc_최시원_09_프리랜서_용역계약_대금지급.txt: PHONE (010)8842-3165
  [오탐] doc_최시원_09_프리랜서_용역계약_대금지급.txt: EMAIL finance@codev.example
  [오탐] doc_최시원_10_구독환불_처리내역서.txt: ACCOUNT 391-910012-34507
  [오탐] doc_최시원_10_구독환불_처리내역서.txt: EMAIL cx@codev.example
  [오탐] doc_최시원_11_휴직신청_면담기록.txt: EMAIL hr@codev.example
  [오탐] doc_최시원_12_워크숍_참가자명단.txt: EMAIL ga@codev.example
  [놓침] doc_최시원_13_사진_재직증명서.png: EMAIL hyun.namgung88@mail.example
  [오탐] doc_최시원_13_사진_재직증명서.png: EMAIL hyun.namgungs8@mail.example
  [놓침] doc_최시원_15_경조사비_신청서.docx: PHONE 031-704-2286
  [오탐] doc_최시원_15_경조사비_신청서.docx: EMAIL ga@codev.example
  [놓침] doc_최시원_16_개인정보유출의심_신고서.txt: CARD 5389201466720153
  [오탐] doc_최시원_16_개인정보유출의심_신고서.txt: EMAIL privacy@codev.example
  [오탐] doc_최시원_16_개인정보유출의심_신고서.txt: EMAIL support@partner-ops.example
  [놓침] doc_최시원_17_출장비_정산서.pdf: CARD 4890123456781234
  [오탐] doc_최시원_17_출장비_정산서.pdf: EMAIL finance@codev.example
  [놓침] doc_최시원_18_스캔PDF_입사지원서.pdf: PASSPORT M71839264
  [오탐] doc_최시원_20_서버정기점검_공지.docx: EMAIL infra-oncall@codev.example

유형      정답  찾음  맞음  재현율  정밀도
ACCOUNT      9    11     9    100%     82%
CARD         3     0     0      0%       -
DRIVER       1     1     1    100%    100%
EMAIL       16    31    15     94%     48%
PASSPORT     2     0     0      0%       -
PHONE       24    21    21     88%    100%
RRN          5     5     5    100%    100%
전체          60    69    51     85%     74%

검사 불가로 차단된 문서: 1개 ['doc_최시원_14_흐린스캔_입사서류동의서.png']
※ 민감정보(SENSITIVE)는 정규식 대상이 아니라 제외 (v1 LLM 평가에서 측정)
```
