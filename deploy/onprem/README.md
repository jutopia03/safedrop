# 사내(폐쇄망) 설치 안내

외부 AI API 없이 사내 서버 1대에서 SafeDrop을 운영하기 위한 묶음입니다. 문서 내용이 회사 밖으로 나가지 않습니다.

## 필요 환경
| 항목 | 기준 | 근거 |
|---|---|---|
| GPU | NVIDIA 16GB 이상 1대 | 판단 qwen3:8b 약 5.6GB + 설명 exaone3.5:7.8b 약 5.2GB = 약 11GB (`docs/eval/local_llm.md`, RTX 4080 SUPER 측정) |
| 소프트웨어 | Linux, Docker + Compose, NVIDIA 드라이버, NVIDIA Container Toolkit | 컨테이너에서 GPU 사용 |
| 디스크 | 약 15GB 이상 | 모델 약 10GB + 이미지 |
| 네트워크 | 설치 준비 단계에만 인터넷 필요 | 운영 중에는 사내망만 사용 |

## 1. 준비 (인터넷이 되는 PC에서)
```bash
cd deploy/onprem
cp onprem.env.example onprem.env        # 값 채우기: python ../../scripts/gen_secrets.py 출력 붙여넣기 + DEMO_PASSWORD
docker compose build                     # 앱 이미지 (OCR 엔진 포함)
docker compose up -d ollama
docker compose --profile setup run --rm pull-models     # 모델 2개 내려받기 (약 10GB)
```

## 2. 폐쇄망으로 반입
```bash
docker save safedrop:onprem ollama/ollama:latest -o safedrop-images.tar
docker run --rm -v safedrop_ollama-models:/m -v "$PWD":/out alpine tar czf /out/ollama-models.tgz -C /m .
```
`safedrop-images.tar`, `ollama-models.tgz`, 이 폴더를 사내 서버로 옮긴 뒤:
```bash
docker load -i safedrop-images.tar
docker volume create safedrop_ollama-models
docker run --rm -v safedrop_ollama-models:/m -v "$PWD":/in alpine tar xzf /in/ollama-models.tgz -C /m
docker compose up -d
```
(alpine 이미지도 함께 `docker save`로 반입하거나, 사내에 있는 아무 리눅스 이미지로 바꿔도 됩니다)

## 3. 확인
- `http://<서버>:8000/api/health` → `"llm": "qwen3:8b"` 가 보이면 로컬 AI 연결 완료
- 정보보호 관리자 계정으로 로그인 → '성능 측정'에서 AI 민감정보 판단·AI 설명 측정 실행 → `docs/eval/local_llm.md`와 비슷한 수치인지 확인
- 운영 시에는 앞단에 사내 HTTPS 리버스 프록시를 둡니다 (브라우저 WebCrypto·WebRTC는 HTTPS에서 동작)

## 한계 (현재 버전)
- 조직도·규정은 `data/company/`의 파일이라, 바꾸면 이미지를 다시 빌드해야 합니다 (향후: 관리 화면·사내 계정 연동)
- 서버 1대 기준입니다. 중계 파일·세션이 메모리에 있어 여러 대로 늘릴 수 없습니다 (향후: 공유 저장소)
- 이 묶음은 설정 검증(`docker compose config`)과 의존성 설치 검증까지 했고, GPU 서버에서 전체 실행은 아직 하지 않았습니다
