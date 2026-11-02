# 테스트 문서 제출 방법 (GitHub 웹, 명령어 필요 없음)

카톡으로 파일을 보내지 말고 **직접 GitHub에 올려 주세요.** 누가 어떤 데이터를 만들었는지가 커밋 기록으로 남아 평가(팀 협업 30점)의 증빙이 됩니다.

## 준비물 (한 폴더에 모아 두기)
1. 테스트 문서들: `doc_이름_01_인사기록.txt` 처럼 **파일 이름 앞에 `doc_본인이름_`** 을 붙여 주세요 (다른 사람 파일과 이름이 겹치지 않게).
2. 정답 파일 1개: `labels_본인이름.json` (예: `labels_양원석.json`). 형식은 [README.md](README.md)의 "정답 형식"과 같고, 내 문서들의 정답을 `[ ... ]` 안에 모두 넣습니다.
3. (민감정보 문장 담당자만) `sensitive_본인이름.json` — 형식은 [SENSITIVE_GUIDE.md](SENSITIVE_GUIDE.md)

## 올리는 순서 (5단계, 약 5분)
1. 메일 또는 GitHub 알림의 **초대(Invitation) 수락**
2. https://github.com/jutopia03/safedrop/tree/main/data/testset/docs 접속
3. 오른쪽 위 **Add file → Upload files** → 준비한 파일들을 한 번에 끌어다 놓기
4. 아래 **Commit changes** 칸에서
   - 첫 줄: `테스트 문서 추가 (본인이름, 문서 N개)`
   - **Create a new branch for this commit and start a pull request** 선택 (main에 바로 올리지 않기)
   - 브랜치 이름: `testdoc-영문이름` (예: `testdoc-wonseok`)
   - **Propose changes** 클릭
5. 다음 화면에서 **Create pull request** 클릭 → 끝. 팀장이 확인 후 합칩니다.

## 팀장이 수정 요청을 하면
PR 페이지의 댓글을 보고, **같은 브랜치**에서 파일을 고치면 PR에 자동으로 반영됩니다.
(PR 페이지 → Files changed → 파일 오른쪽 `…` → Edit file)

## 체크리스트
- [ ] 모든 개인정보가 **가짜**인가 (실제 사람·번호 금지)
- [ ] 정답 `text`가 문서 속 글자와 **띄어쓰기·하이픈까지 똑같은가**
- [ ] 개인정보처럼 보이지만 아닌 것(대표번호, 제품번호, 날짜 등)을 문서의 30% 정도에 섞었는가 → 정답에는 넣지 않음
- [ ] 파일 이름에 본인 이름을 붙였는가
