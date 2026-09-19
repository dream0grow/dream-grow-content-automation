# 뷰트랩 키워드 발굴 자동화 — 무인 실행 설정 (Aside 없이)

매일 09:00 KST에 `viewtrap_keyword_queue.json`의 pending 키워드 30개를 뷰트랩에서 검색·채점해
벤치마킹 시트에 기록하고, 5점 이상 키워드의 영상을 풀링 탭에 넣는다.
코드: `orchestrator/viewtrap_keywords.py`, 워크플로우: `.github/workflows/viewtrap-keywords.yml`.
사람 승인은 어디에도 없다 (순수 스크립트). Aside 브라우저와 무관하게 GitHub 서버에서 돈다.

## 무엇을 하나 (Aside 세션 2026-09-18에서 손으로 검증한 절차 그대로)

| 단계 | 내용 |
| --- | --- |
| 큐 | `viewtrap_keyword_queue.json` → `status: pending` 키워드를 순서대로 최대 30개. 시트 C열에 이미 있으면 `skipped_in_sheet` |
| 검색 | 뷰트랩 검색 내역에 같은 키워드가 있고 1년 이내면 **횟수 안 쓰고 재사용**, 아니면 새 검색 (`POST contents/videos/request/keyword`) 후 영상 수가 안정될 때까지 폴링 |
| 지표 | F 조회수 합계(만), G 활발성(게시월 히스토그램 마지막 막대/최대 ≥0.55 상, ≥0.25 중), AB~AK 기여도·성과도 분포, J 조회수 중앙값·K 구독자 중앙값(API 값으로 직접 계산) |
| 시트 | "잠재고객키워드수요(풀링)" 탭 첫 빈 행부터 A~AK (H/I/M/N~S는 기존과 같은 수식, H:I는 0.0% 서식) |
| 풀링 | 결과 5점 이상 → "풀링 영상 만들기" 탭에 쇼츠 제외 조회수 상위 5개 + 교육·육아 채널 선별 5개(라벨에 `(교육·육아 채널)`), 행 높이 150 |
| 마무리 | 큐 파일 갱신·커밋, 텔레그램 요약. 잔여 검색 횟수가 40 미만이면 새 검색 중단 |

## 1회 설정 (약 10분)

### 1) `VIEWTRAP_COOKIE` 시크릿 (뷰트랩 로그인)
뷰트랩은 httpOnly 세션 쿠키로 인증한다 (쿠키 없으면 HTTP 412).
1. 브라우저에서 https://app.viewtrap.com/video-search 를 뷰트랩 멤버십 계정으로 로그인한 상태로 열기.
2. 개발자도구(F12) → **Network** 탭 → 목록에서 `api.viewtrap.com` 요청 하나 클릭 (예: `notifications`, `histories/keyword`).
3. **Request Headers**의 `cookie:` 값 **전체**를 복사.
4. GitHub 저장소 → Settings → Secrets and variables → Actions → **New repository secret**
   - Name `VIEWTRAP_COOKIE`, Value: 복사한 값 그대로.
5. 쿠키가 만료되면 파이프라인이 **텔레그램으로 "VIEWTRAP_COOKIE 갱신 필요"** 알림을 보내고 그날은 종료한다 → 2~4 반복.

#### 쿠키 자동 유지 (2026-09-19 추가, 검증 중)
- 뷰트랩 세션 토큰(`token` 쿠키, JWT)은 **발급 후 7일** 유효하다. 앱에는 갱신 API가 없고 로그인은 Google 버튼뿐이다.
  그런데 2026-09-17에 Google 재로그인 없이 같은 ticket으로 새 토큰이 발급된 적이 있다 → 서버가 만료 직전/직후 요청에
  토큰을 재발급하는 것으로 보인다 (평소 요청에는 Set-Cookie 없음, 확인됨).
- 그래서 워크플로우가 **6시간마다 `--touch-only`**(검색 없이 `auth/users` 호출)로 API를 건드리고, 응답에 새 `token`이 오면
  `VIEWTRAP_COOKIE_KEY`로 암호화해 `data/viewtrap_session.enc`에 커밋한다. 이후 실행은 환경변수 쿠키와 저장 쿠키 중
  만료가 더 늦은 쪽을 쓴다 (사람이 새 쿠키를 붙여넣으면 그것이 자동으로 우선). 재발급이 저장되면 텔레그램으로 "쿠키 자동 갱신됨" 알림.
- **이 재발급이 실제로 온다는 보장은 없다.** 첫 만료(이번 쿠키는 9/24 11:13) 전후에 "자동 갱신됨" 알림이 오면 이후는 손대지 않아도 되고,
  "갱신 필요" 알림이 오면 서버가 재발급하지 않는 것이므로 주 1회 수동 교체가 필요하다. 만료된 Google 자격증명(`v_provided_key`)으로
  `/auth/login`을 다시 부르는 것은 500(C9999)으로 거부되는 것을 확인했다 (Google 토큰 만료 검사함).
- 수동 교체가 번거로우면 대안: (a) 뷰트랩에 로그인된 브라우저가 있는 Mac에서 launchd로 쿠키 DB를 읽어 `gh secret set`하는 스크립트
  (Keychain 접근 허용 필요, Mac이 켜져 있을 때만), (b) 뷰트랩 대신 YouTube Data API로 같은 지표를 계산(yt-research에 이미 기여도·성과도 로직이 있음,
  단 하루 30키워드는 기본 쿼터 10,000을 넘어 기준 조정 필요).

### 1-b) `VIEWTRAP_COOKIE_KEY` (등록됨)
재발급 토큰을 공개 저장소에 암호화해 놓기 위한 임의 문자열. 바꾸면 기존 `data/viewtrap_session.enc`는 무시된다(복호 실패 → 환경변수 쿠키 사용).

### 2) `GSHEET_SA_JSON` (이미 있음)
썸네일 파이프라인이 쓰는 서비스 계정을 그대로 쓴다 (`docs/thumbnail-sheet-setup.md`). 같은 스프레드시트
(`1Vy6_9gn3nNovUUdTqYOmkuc4ZamNbj-5tlvZ1fHmN24`)에 편집자로 공유돼 있으면 추가 설정 없음.

### 3) (선택) 텔레그램·LLM
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`가 있으면 매일 요약을 받는다 (이 저장소에 이미 등록됨).
`CLAUDE_CODE_OAUTH_TOKEN`(이미 등록됨, Claude Code CLI 경로) 또는 `ANTHROPIC_API_KEY`가 있으면 5점 키워드의
"교육·육아 채널" 영상 선별을 Claude가 한다. 둘 다 없으면 정규식 휴리스틱으로 대체된다(정밀도 낮음).

### 4) 워크플로우 활성화
`.github/workflows/viewtrap-keywords.yml`이 **기본 브랜치**에 있어야 cron이 돈다 (GitHub 규칙).
개발 브랜치에서 작업했다면 main에 머지한다. 수동 실행: Actions → viewtrap-keywords → Run workflow
(`dry_run=true`로 먼저 계획만 확인 가능).

## 로컬에서 돌리기
```bash
pip install requests python-dotenv google-auth pyyaml
export VIEWTRAP_COOKIE='...'   # 위 1)
export GSHEET_SA_JSON="$(cat 서비스계정.json)"
python3 -m orchestrator.viewtrap_keywords --dry-run      # 계획만
python3 -m orchestrator.viewtrap_keywords --limit 30     # 실제 실행
```

## 키워드 추가
`viewtrap_keyword_queue.json`의 `keywords` 배열에 `{"keyword": "...", "status": "pending", "source": "..."}`를
끝에 붙이면 다음 실행 때 순서대로 처리된다. 상태값: pending / done / error / skipped_in_sheet.

## Orca에서 돌리고 싶다면 (대안)
Orca에는 **Automations**(예약 프롬프트)가 있어 매일 09:00에 에이전트를 띄울 수 있다:
```bash
orca automations create --name "뷰트랩 키워드 30개" --trigger daily --time 09:00 \
  --provider claude --repo id:<repoId> \
  --prompt "docs/viewtrap-keywords-setup.md 의 절차대로 python3 -m orchestrator.viewtrap_keywords --limit 30 을 실행하고 결과를 요약해라. VIEWTRAP_COOKIE가 만료(HTTP 412)면 Orca 내장 브라우저로 app.viewtrap.com 에 로그인된 세션의 쿠키를 다시 읽어 .env를 갱신한 뒤 재실행해라."
```
전제: (1) Orca가 09:00에 켜져 있어야 한다 — 노트북을 닫으면 안 되므로 항상 켜둔 Mac/Mac mini에서
Orca를 띄우거나 `orca serve`(Remote Orca Server)를 쓴다. (2) `.env`에 `VIEWTRAP_COOKIE`, `GSHEET_SA_JSON`
(3) Claude Code 승인 프롬프트를 없애려면 저장소 `.claude/settings.json`의 `permissions.allow`에
`Bash(python3 -m orchestrator.viewtrap_keywords*)`를 넣거나 `permissions.defaultMode`를 `bypassPermissions`로 둔다.
장점: Orca 내장 브라우저(세션 유지)로 로그인해 두면 쿠키 만료 시 에이전트가 스스로 갱신할 수 있다.
단점: 항상 켜진 머신이 필요하고, 배치 작업치고는 구성 요소가 많다. **매일 무인 실행만 원하면 GitHub Actions가 더 단순하다.**

## Aside 루틴으로 유지하려면
Aside 앱이 09:00에 켜져 있어야 한다. 승인 없이 돌리려면 루틴 권한을 `full-access`로 바꾼다
(스킬 `~/.aside/u/0/skills/user/viewtrap-keyword-pipeline/`). 두 곳에서 동시에 돌리면 같은 큐를 두 번
처리하므로 하나만 켜둘 것.

## 주의
- 뷰트랩 약관에 "자동화된 봇·스크립트 이용 금지, 위반 시 계정 제한" 조항이 있다. 이 스크립트는 그 조항을
  피하지 못한다 (하루 30회, 검색 간 8~15초 대기로 부담만 줄임). 계정 제한 위험은 사용자가 감수하는 것.
- 뷰트랩 필터 패널의 '조회수 중앙값'과 '구독자 중앙값' 라벨은 서로 바뀌어 표시된다(2026-09 확인).
  시트 3~61행은 2026-09-18에 J/K를 맞바꿔 바로잡았고, 스크립트는 API 원본으로 계산한다.
- 일반 명사(수업, 감정, 장난감 등)는 대형 채널 영상 때문에 점수가 높게 나온다. "아이 ○○"처럼 학부모 검색어
  형태가 더 유의미하다.
- 큐 파일은 워크플로우가 커밋하므로, 로컬에서 큐를 고쳤으면 push한 뒤 다음 실행을 기다린다 (충돌 방지).
