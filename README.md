# SafeDrop

민감정보 판단 AI Agent 기반 **안전한 사내 파일 전송 채널** — 코디세이 AI 네이티브 Final-Project, 팀 codev

## 한 줄 소개
파일을 보내기 직전, 사내 분석 서버가 파일 속 개인정보를 찾고 **수신자별로 허용·마스킹·차단**을 판단해 근거 조항과 함께 알려준 뒤, 허가된 파일만 브라우저 간 전송합니다.

## 문서
- [요구사항 명세](docs/requirements.md) — 문제 정의, 사용자 흐름, 기능·비기능 요구사항과 달성 현황
- [아키텍처](docs/architecture.md) — 시스템 구성도, 데이터 파이프라인, 전송 흐름, 보안 설계
- [개발 과정과 핵심 개념](docs/understanding.md) — 단계별(S1~S8) 결정과 측정 결과
- [멘토 피드백 반영 내역](docs/mentor-feedback.md) — 피드백별 판단·반영 내용과 근거 커밋

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
pip install -r requirements-dev.txt && pytest -q   # 자동 테스트 (LLM·네트워크 없이 1초 내)
uvicorn backend.app.main:app --reload
# 브라우저에서 http://localhost:8000
```

## 배포 (Render 무료 웹 서비스)
1. [render.com](https://render.com)에 GitHub 계정으로 가입 (카드 불필요)
2. New → **Blueprint** → 이 저장소 선택 → `render.yaml` 설정으로 생성
3. 배포 완료 후 `https://<서비스이름>.onrender.com` 접속
- 무료 플랜은 15분 동안 요청이 없으면 잠들고, 다음 접속 때 약 1분 걸려 깨어남 → 시연·테스트 직전에 한 번 접속해 깨워 둘 것
- 잠들었다 깨면 서버 메모리(서명 키, 중계 대기 파일)가 초기화됨 → 그 전에 발급된 토큰은 무효
- API 키는 Render 대시보드 Environment에 입력 (저장소에 커밋 금지): `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` (`.env.example` 참고)
- **로그인 설정(필수)**: `DEMO_PASSWORD` = 시연 비밀번호(팀·심사위원에게만 공유). 비워두면 기본값이라 누구나 로그인 가능하니 반드시 설정. 선택: `SESSION_SECRET`(임의의 긴 문자열) — 설정하면 서버가 재시작돼도 로그인이 유지됨

## 로그인과 권한
- 가상 직원을 고르고 시연 비밀번호로 로그인. 브라우저 **탭마다 다른 직원**으로 로그인 가능(탭별 세션)
- 발신자는 서버가 로그인 세션에서 정함(다른 사람 행세 불가). 중계 파일은 수신자 본인만, 허가 토큰의 발신자 본인만 올릴 수 있음
- 감사 로그·성능 측정은 **정보보호 관리자(표준혁)** 계정에서만 보임
- 업로드는 10MB까지, 로그인 실패는 IP당 1분 5회까지

## 성능 측정
관리자(표준혁)로 로그인 → 화면 아래 '성능 측정' 버튼. 처음 누르면 측정 시작, 1~2분 뒤 다시 누르면 결과가 나옵니다('다시 측정' 체크 후 누르면 재측정).
- `/api/eval/detect` 정규식 탐지 재현율·정밀도 (테스트 문서 세트)
- `/api/eval/retrieval` 근거 조항 검색 Recall@1·@3
- `/api/eval/sensitive` AI 민감정보 판단 정확도 (AI 사용, 30초 간격 제한)
- `/api/eval/explain` AI 설명 인용 검증 통과율 (AI 사용, 30초 간격 제한)

## 개발 단계
- [x] S1 뼈대 + 가상 기업 데이터
- [x] S2 텍스트 추출 + 정규식 탐지 (+ 추출 불가 시 차단)
- [x] S3 규칙표 기반 수신자별 판정 + 마스킹
- [x] S4 전송 허가 토큰 + 전송 + 화면
- [x] S5 v0 통합·배포 (베이스라인 측정은 테스트 문서 도착 후)
- [x] S6 v1 LLM 애매 문장 판단 (실제 키로 성능 측정 예정)
- [x] S7 v2 근거 조항 검색(RAG) + AI 설명 + 인용 검증
- [ ] S8 사용자 테스트·피드백 반영
