# SafeDrop

민감정보 판단 AI Agent 기반 **안전한 사내 파일 전송 채널** — 코디세이 AI 네이티브 Final-Project, 팀 codev

## 한 줄 소개
파일을 보내기 직전, 사내 분석 서버가 파일 속 개인정보를 찾고 **수신자별로 허용·마스킹·차단**을 판단해 근거 조항과 함께 알려준 뒤, 허가된 파일만 브라우저 간 전송합니다.

## 폴더 구조
```
backend/app/   FastAPI 서버 (탐지·판정·토큰·전송 API)
web/           화면 (HTML/JS)
data/company/  가상 기업 데이터: 조직도, 사내 규정, 규칙표
data/testset/  성능 측정용 테스트 문서와 정답
docs/          설계·개발 과정 문서
```

## 실행 (로컬)
```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
# 브라우저에서 http://localhost:8000
```

## 개발 단계
- [x] S1 뼈대 + 가상 기업 데이터
- [ ] S2 텍스트 추출 + 정규식 탐지 (+ 추출 불가 시 차단)
- [ ] S3 규칙표 기반 수신자별 판정 + 마스킹
- [ ] S4 전송 허가 토큰 + 전송 + 화면
- [ ] S5 v0 통합·배포·베이스라인 측정
- [ ] S6 v1 LLM 애매 문장 판단
- [ ] S7 v2 근거 설명 + 인용 검증
- [ ] S8 사용자 테스트·피드백 반영
