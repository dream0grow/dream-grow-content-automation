# 🌿 스피드 곶자왈 퀴즈 게임

곶자왈(제주)의 **식물·나비·새·곤충**을 배우며 달리는 단일 HTML 게임.
캐릭터가 달리다 돌이 굴러오면 퀴즈를 풀어 **돌을 던져 부수고**, 틀리면 큰 돌에 맞아 ❤️ 가 줄어요.
3단계(식물 → 나비·새 → 곤충·곶자왈의 비밀), 단계마다 10문제. 빨리 완주할수록 랭킹 상위!

## 파일

| 파일 | 설명 |
|---|---|
| `index.html` | 게임 본체. 라이브러리·빌드 없이 브라우저에서 바로 열림(Canvas) |
| `QUIZ.md` | 30문제 + 정답·해설 (검토·수정용) |
| `share-qr.png` | 배포 주소 공유용 QR |

## 바로 해보기 (로컬)

`index.html` 파일을 더블클릭해서 브라우저로 열면 끝.

## 배포 (GitHub Pages)

`.github/workflows/deploy-game.yml` 가 `games/` 폴더를 Pages로 자동 배포한다.

- **최초 1회 설정**: 저장소 **Settings → Pages → Source = "GitHub Actions"** 로 지정
- main에 `games/` 변경이 push되면 자동 배포 (수동: Actions → *Deploy game to GitHub Pages* → Run)
- 배포 주소: **https://dream0grow.github.io/dream-grow-content-automation/gotjawal-quiz/**

## 문제 추가·수정

`index.html` 의 `STAGES[n].qs` 배열에서
`{ q:"질문", a:"정답", w:["오답1","오답2"] }` 형식으로 더하거나 고치면 된다.
같은 내용을 `QUIZ.md` 에도 반영해 두면 관리가 편하다.

## 한계 / 다음 단계

- 랭킹은 현재 **브라우저(localStorage)** 에만 저장 → 같은 기기·링크에서 겨루기. 여러 기기 통합 랭킹은 서버(예: Cloudflare Worker + KV)가 필요.
- 발행·검수 전 `QUIZ.md` 의 사실관계를 도감/제주도 자료로 한 번 더 확인 권장.
