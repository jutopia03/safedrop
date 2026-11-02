# 로컬 LLM(Ollama) 측정 안내 (팀원용)

## 왜 하나
SafeDrop의 대상은 **외부 클라우드를 쓸 수 없는 회사**입니다. 그런 회사는 문서 내용을 외부 AI API로 보낼 수 없으니, 사내 GPU 서버에서 도는 로컬 모델이 필요합니다.
멘토·퍼실리테이터가 물은 두 가지에 **숫자로** 답하는 게 목적입니다.
- "온프레미스라면 어떤 LLM을, 어느 정도 인프라로?" → 모델별 정확도 + GPU 메모리 + 시간
- "Ollama를 쓴다면 왜?" → 외부 API(gpt-5-mini) 대비 품질이 어느 정도인지

## 준비 (처음 한 번, 약 20~30분)
1. **Ollama 설치**: https://ollama.com/download → 설치 후 터미널(PowerShell)에서 `ollama --version` 이 나오면 OK
2. **Python 3.11 이상** 설치 확인: `python --version`
3. **코드 받기**: https://github.com/jutopia03/safedrop → 초록색 `Code` → `Download ZIP` → 압축 풀기
   (git을 쓸 줄 알면 `git clone` 도 OK. **측정 직전에 최신 버전을 받아 주세요** — 팀원들의 민감정보 문장 세트가 합쳐진 뒤여야 정확도 측정이 됩니다)
4. 압축 푼 폴더에서 터미널을 열고: `pip install -r requirements.txt`
5. **모델 받기** (RTX 4080 16GB 기준, 각각 5~10GB 다운로드):
   ```
   ollama pull qwen3:8b
   ollama pull exaone3.5:7.8b
   ollama pull qwen3:14b
   ```
   - 고른 기준: 한국어를 잘하는 공개 모델 중 **16GB GPU에 올라가는 크기**. qwen3(알리바바, 다국어), exaone3.5(LG AI연구원, 한국어 특화), 같은 계열 크기 비교용 qwen3:14b
   - 이름이 바뀌어 pull이 실패하면 https://ollama.com/library 에서 비슷한 크기의 모델로 바꾸고, 바꾼 이유를 PR에 적어 주세요

## 측정 (모델당 수 분~수십 분)
압축 푼 폴더에서 모델마다 한 번씩:
```
python scripts/bench_local.py qwen3:8b
python scripts/bench_local.py exaone3.5:7.8b
python scripts/bench_local.py qwen3:14b
```
- 끝나면 `docs/bench/ollama_<모델>.md` 파일이 생깁니다 (정확도, 걸린 시간, GPU 메모리 최고 사용량, 모델 크기가 자동 기록됨)
- 측정 중에는 게임·영상 등 GPU를 쓰는 프로그램을 꺼 주세요 (메모리 수치가 섞입니다)
- "민감정보 문장 세트가 아직 없습니다"가 나오면: 설명 품질 측정만 된 것이니, 문장 세트가 합쳐진 뒤 최신 ZIP으로 한 번 더 돌려 주세요

## 제출 (GitHub 웹, 약 5분)
[테스트 문서 제출 방법](../../data/testset/SUBMIT.md)과 같은 방식입니다. 업로드 위치만 다릅니다.
1. https://github.com/jutopia03/safedrop/tree/main/docs/bench 접속 → `Add file → Upload files`
2. 생성된 `ollama_*.md` 파일들을 끌어다 놓기
3. 커밋 메시지 `로컬 LLM 측정 결과 (모델 N개)` → **Create a new branch** (`bench-영문이름`) → `Propose changes` → `Create pull request`
4. PR 설명에 한두 줄: 측정하며 느낀 점 (예: 첫 응답이 느렸다, 14b는 메모리가 빠듯했다)

## 문제가 생기면
| 증상 | 해결 |
|---|---|
| `connection refused` | Ollama가 꺼져 있음 → 작업 표시줄에서 Ollama 실행, 또는 터미널에서 `ollama serve` |
| 시간 초과(timeout) 반복 | 모델이 너무 큼 → 작은 모델로 측정하고 PR에 기록 |
| GPU 메모리가 `?` | `nvidia-smi` 명령이 안 되는 것 → 그래픽 드라이버 확인. 결과는 그대로 올려도 됨 |
| 한글이 깨져 보임 | 결과 파일은 UTF-8로 저장됨. GitHub에 올리면 정상 표시 |
