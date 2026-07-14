# 드림그로우 콘텐츠 자동화 — 프로젝트 컨텍스트

> 이 파일은 새 세션이 자동으로 읽는다. 작업을 이어가려면 `/dreamgrow-resume` 스킬을 호출하라.
> 지난 세션 기록(2026-06~07)은 `docs/HISTORY.md`에 있다.
> 마지막 갱신: 2026-07-07

## 무엇을 만들고 있나

초등 학부모 교육 브랜드 "드림그로우"의 콘텐츠를 **멀티 에이전트 파이프라인**으로 자동 생산·발행한다.
GitHub Actions가 cron으로 카드 저장소를 폴링하고, 사람은 모바일에서 카드 생성·승인만 한다.

흐름: `intake → 리서치 → 키워드 점수화 → ⏸️키워드 승인(자동승인 기본 ON) → 브리프 → 작가↔비평가↔검수 토론 초안 → 검수/평가 → ⏸️발행 승인 → 발행(Threads/스티비)`

**저장소 = 옵시디언 볼트 하나** (노션 철수 완료). 카드는 `vault/파이프라인/활성/<id> <제목>.md`,
frontmatter가 라우팅 속성(stage/status/approval_status…), 본문 `## 섹션`이 단계 산출물이다
(`orchestrator/obsidian_state.py`, 볼트 경로 `DG_VAULT_ROOT` 기본 `vault/`). 호출부는 파사드
`orchestrator/state.py`(`from orchestrator import state as store`)만 본다.
**동기화는 GitHub Actions가 `vault/`를 커밋·push하는 git/GitHub 단일 경로다** (노션·Obsidian Sync 아님).
승인·발행 알림은 텔레그램으로 나간다. 이관 경위는 `docs/HISTORY.md`, 기준 사양 `docs/기획/통합기획_v3.md`.

상세 설계: `docs/ARCHITECTURE_V2.md`

## 핵심 ID / 리소스

- 개발 브랜치: **`claude/dreamgrow-orchestrator-review-z4zo4b`** (모든 작업은 여기서, main에 PR로 머지)
- 저장소: `dream0grow/dream-grow-content-automation`
- 카드 저장소: 옵시디언 볼트 `vault/파이프라인/{활성,발행완료}/` (별도 DB 없음, git으로 동기화)
- 볼트 경로 override: `DG_VAULT_ROOT` (기본 `vault/`)
- 알림 채널: 텔레그램 (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`)

## 코드 구조 (`orchestrator/`)

| 파일 | 역할 |
|---|---|
| `run.py` | stage 상태 머신 (DISPATCH) + 고아 청소·실패 재시도. cron이 `python3 -m orchestrator.run` 실행 |
| `state.py` | 저장소 파사드 — 옵시디언 볼트 백엔드를 노출. 호출부(`store`)는 이 모듈만 본다 |
| `obsidian_state.py` | 볼트 카드 저장소 — `vault/파이프라인/` md 카드 읽기/쓰기, 텔레그램+결재함 알림(`notify`) |
| `prompts.py` | 브랜드 보이스/룰북 + 에이전트 프롬프트 (리서치/키워드/브리프/작가/비평가/검수/평가/회고) |
| `agent_dialogue.py` | 작가↔비평가↔검수 토론 루프 + 벤치마킹/후킹 로드 |
| `manus_research.py` | Manus 외부 리서치(전담). 25분 내 결과 없으면 Claude 폴백 |
| `naver_keywords.py` | 네이버 검색광고 API로 키워드 실측 검색량/경쟁도 |
| `publish.py` | publish_ready 카드 발행 (Threads 체인 / 스티비 뉴스레터) |
| `stibee.py` | 스티비 3단계 발행: POST /emails → POST /emails/{id}/content(text/html) → /send |
| `style_learn.py` | AI 원본 vs 사람 수정본 diff → Honcho 문체 학습 |
| `self_improve.py` | 주간 회고 → 프롬프트 개선 큐시트(사람 승인 후 반영) |
| `daily_intake.py` | 매일 새 주제 자동 발제 → intake 카드 생성 (이후 오케스트레이터가 초안까지 자동) |
| `preview.py` | 발행 직전 드라이런: 초안 생성 후 스레드 분할/뉴스레터 HTML 렌더 (시크릿·발행 없이) |
| `cardnews.py` | 초안 → 실사진 오버레이 카드뉴스 PNG (Pretendard, Playwright/Chromium) |
| `stock.py` | 실물 스톡 사진 검색 (Pexels/Unsplash, 상업 라이선스) |
| `image_gen.py` | AI 배경 이미지 생성 (OpenAI gpt-image-1 / Google Imagen, 한국인 중심) |
| `cardnews_benchmark.py` | 최근 뜬 카드뉴스 벤치마킹 리서치(Manus/Claude) → `data/cardnews_benchmark.md`, 카드 생성 시 주입 |
| `config.py` | 환경변수 한 곳 관리 |

데이터: `data/benchmark_posts.md`(스레드 7구조·12훅·변주, CSV 분석), `data/hook_patterns.md`(후킹 패턴).
워크플로우: `.github/workflows/orchestrator.yml`(30분 cron), `daily-intake.yml`(매일 07:10 KST 새 주제 발제),
`self-improve.yml`(주간), `test-stibee.yml`(수동 발송 테스트), `test-cardnews.yml`(카드뉴스 실제 생성 테스트).

## 카드뉴스 / 발행 미리보기 (2026-07-01)

- **미리보기(`preview.py`)**: `--topic`으로 초안 생성 후 스레드 분할/뉴스레터 HTML을 파일로 렌더. 발행·시크릿 불필요.
- **카드뉴스(`cardnews.py`)**: 초안 → 슬라이드(표지·본문·마무리) → 실사진 풀블리드 + Pretendard 볼드 오버레이 PNG(1080²).
  - 배경 사진 우선순위(`DG_PHOTO_ORDER`, 기본 `owned,stock,generate`): ①`--photos-dir` 소유 사진
    ②실물 스톡(`stock.py`: `PEXELS_API_KEY`/`UNSPLASH_ACCESS_KEY`) ③AI 생성(`image_gen.py`: `GOOGLE_API_KEY` Imagen
    또는 `OPENAI_API_KEY` gpt-image-1, 한국인 중심) ④그라데이션 폴백.
  - Pretendard는 `ensure_fonts()`가 GitHub에서 받아 설치. Chromium은 로컬 `/opt/pw-browsers` 또는 Actions `playwright install`.
  - 실행/검증: `test-cardnews.yml`(수동, 주제 입력 → PNG 아티팩트). 사진 API는 인터넷 개방된 Actions에서 동작.

## 사람 병목 최소화 (2026-07-01)

사람은 **마지막 발행 승인만** 하도록 설계. 그 앞 단계는 전부 자동:
- **키워드 자동승인 기본 ON** (`config.AUTO_APPROVE_KEYWORD`): 최고점 키워드 자동 채택 → 브리프·초안까지 자동.
  끄려면 `DG_AUTO_APPROVE_KEYWORD=false`.
- **초안 완성 시 텔레그램 알림**: `handle_keyword_approved`가 발행 승인 게이트에서 `notify()` 호출
  → 텔레그램 폰 알림 + 볼트 `_system/review_queue.md` 결재함 기록.
- **매일 자동 발제**: `daily-intake.yml`이 하루 1회 `daily_intake.py` 실행 → 새 주제 카드 생성.
  개수는 `DG_DAILY_TOPIC_COUNT`(기본 1), 대상은 `DG_DEFAULT_AUDIENCE`(기본 "초등 저학년 학부모").

## 환경변수 / GitHub Secrets

필수: (`ANTHROPIC_API_KEY` 또는 `CLAUDE_CODE_OAUTH_TOKEN`)
선택: `DG_VAULT_ROOT`(기본 `vault/`), `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`(알림),
`MANUS_API_KEY`, `HONCHO_API_KEY`, `NAVER_AD_API_KEY`/`NAVER_AD_SECRET`/`NAVER_AD_CUSTOMER_ID`,
`THREADS_ACCESS_TOKEN`/`THREADS_USER_ID`, `STIBEE_API_KEY`/`STIBEE_LIST_ID`/`STIBEE_SENDER_EMAIL`/`STIBEE_SENDER_NAME`/`STIBEE_AUTO_SEND`,
`DG_AUTO_APPROVE_KEYWORD`(기본 ON), `DG_DAILY_TOPIC_COUNT`(기본 1),
`DG_DEFAULT_AUDIENCE`(기본 "초등 저학년 학부모")

## 운영 — 자주 하는 작업

카드는 볼트 `vault/파이프라인/활성/`의 md 파일이다. 승인은 카드 frontmatter를 바꾸는 것
(옵시디언/텔레그램). 사람이 바꾼 frontmatter를 cron이 감지해 다음 단계를 돌린다.

- **새 글 만들기**: `vault/파이프라인/활성/`에 카드 생성 (frontmatter `stage: intake`, `status: queued`,
  `format: thread`/`newsletter`/`youtube`(유튜브 롱폼 원고, 콤마 혼합 가능), `audience` 입력).
  매일 발제(`daily-intake`)와 yt_research 사이트 「파이프라인 발제 🚀」도 카드를 만든다.
- **키워드 승인**: 키워드 섹션 확인 → `approved_keyword`에 키워드(또는 부모 고민 문장) 입력 + `approval_status: approved`
- **발행 승인**: 초안/검수 확인 → `review_status: approved`이면 `approval_status: approved` → 자동 발행
- **수정 요청**: 카드 `📝 수정 요청` 섹션에 지시 적고 `approval_status: revision_requested` → 재초안
- **orchestrator 수동 실행**: GitHub Actions 탭 → orchestrator → Run workflow (Claude는 권한상 직접 실행 불가, 사용자가 클릭)
- **대량 검토 생성**: `DG_AUTO_APPROVE_KEYWORD=true` → 키워드 자동 채택 → 초안까지 자동 (발행만 사람)

## 알아둘 제약

- Claude(이 세션)는 GitHub Actions 워크플로우를 **직접 실행 못 함**(403). 사용자가 Run workflow 클릭해야 함.
- 볼트 카드는 md 파일이라 Glob/Grep/Read로 직접 읽는다. 본문이 크면 python 슬라이스로 읽기.
- 볼트 동기화는 git 하나뿐 — 여러 워크플로우가 같은 브랜치에 push하므로 `pull --rebase → push`를 재시도한다.
- cron이 정시(00/30분)엔 자주 누락 → `8,23,38,53분`으로 설정함. 불안정하면 수동 실행.
- Manus listMessages는 structured output을 안 줌 → 25분 후 Claude 폴백이 정상 동작(품질 좋음).

## 현재 상태 (세션마다 갱신)

### 에이전트 OS 점검 + 텔레그램 핑퐁 전면 확장 (2026-07-13, main 머지 완료) — ⬅️ 이번 세션 작업

- **daily-intake 7일 연속 실패 수리** (#58): 워크플로우가 미설정 시크릿을 빈 문자열로 넘겨
  `int('')` 크래시(2026-07-07~12 전건 실패). `daily_intake.py` env 파싱을 `or` 폴백으로 교체.
- **새 카드 접수 텔레그램 통지** (#59): `handle_intake`가 `🆕 새 카드 접수`(ID+주제)를 notify —
  매일 발제·사이트 발제 모두 커버. 생성→초안→발행 전 과정이 폰 알림으로 이어진다.
- **핑퐁 전면 확장 — 파이프라인 카드도 답장 수정** : `script_feedback.py`가 피드백 target의
  카드 ID(DG-YYYY-NNNN)를 인식, 활성 카드에 `📝 수정 요청` 섹션 기록 + `approval_status:
  revision_requested`로 디큐(여기선 LLM 안 부름 — run.py `handle_revision_requested`가 재초안).
  yt_research 웹훅도 카드 ID 추출 추가(그쪽 PR#15). 즉 **스레드/뉴스레터 카드(→카드뉴스),
  유튜브 롱폼·스레드·릴스 원고 파일 전부 텔레그램 답장으로 수정**된다.
- **알림 대상 확대**: `05 리뷰/대기` 알림을 youtube-script 한정 → 전 형식으로. 폭주 방지로
  비-youtube는 frontmatter 생성일 `DG_ANNOUNCE_MAX_AGE_DAYS`(기본 7일) 이내만, `상태: 발행완료`
  등은 제외. 빈 YAML 값(`검수상태:`)이 None으로 파싱돼 걸러지던 버그도 수리(`or ""`).
- 사용자가 `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` 시크릿 설정 완료(2026-07-13) — 알림 라이브.
- **알림에서 바로 읽기**: `obsidian_state.notify()`가 카드 GitHub blob 링크를 항상 첨부 —
  텔레그램에서 누르면 카드가 열린다.
- **초안 열람 사본**(`orchestrator/review_copy.py`): thread/newsletter 초안 완성 시
  `05 리뷰/대기/{스레드|뉴스레터}_{주제}.md`(기존 파일명 규칙)로 사본 저장 → script_feedback이
  링크 포함 알림. frontmatter `content_id`로 원본 카드를 가리켜, 이 파일명으로 온 피드백은
  **카드 재초안으로 라우팅**(사본 직접 수정은 발행에 반영 안 됨 — 파일 상단에 경고 주석).
  재초안 시 같은 파일명으로 덮어써 항상 최신 초안을 비춘다. 발행 원본은 여전히 카드다.
- **소크라테스 질문 맥락 고정**(`vault_pipeline/socrates.py`, `.claude/agents/zk-socrates.md`):
  "교실 0.1x/제도 10x" 강제 프레임 제거. 노트의 주제 영역(비즈니스/교육/방법론)을 먼저 파악해
  **그 주제 안에서** 전제 검증·반례와 경계·재정의/다음 단계를 묻는다(맥락 갈아끼우기 금지).
- 테스트 59종 통과(신규: intake 통지 1, 카드 핑퐁 2, 알림 확대 2, 사본 라우팅 1, 사본 내보내기 1 등).
- 미결: DG-2026-0001 발행 승인 대기(사용자), DG-2026-0002 큐시트 승인 대기.

### 유튜브 롱폼 원고 자동화 (2026-07-13, 병렬 세션, main 머지 완료)

`format: youtube` 카드가 들어오면 리서치→키워드→브리프는 기존 그대로 타고, 초안 단계에서
**유튜브 롱폼 원고**(제목·썸네일 문구 + 30초 도입부 + 타임스탬프 본문 + 제작 메모)를 자동으로 쓴다.
신규 `orchestrator/youtube_script.py` + `prompts.YOUTUBE_SCRIPT`(HUMANIZE_RULES 주입) + 테스트 6종(전체 52종 통과).
- **인계 경로**: 원고를 `05 리뷰/대기`에 사이트와 동일한 frontmatter(`type: youtube-script`,
  `검수상태: 대기`)로 저장 → 기존 `script_feedback`(같은 orchestrator.yml 실행)이 파일명 포함
  텔레그램 알림 → 답장하면 수정 반영 핑퐁. **발행 게이트 없음** — 유튜브 원고의 종착지는 촬영.
- **유튜브 전용 카드**: 원고 인계 후 `stage: published, status: done`으로 완료 + 통지.
  혼합(`thread, youtube`)이면 유튜브 원고는 별도 저장하고 thread/newsletter는 기존 승인 게이트 진행
  (유튜브 생성 실패 시 통지 후 thread 흐름 계속).
- **발제 입구**: yt_research 사이트 「파이프라인 발제 🚀」에 "유튜브 원고 🎬" 옵션 추가
  (`lib/pipeline.ts` format: youtube). 카드 직접 생성 시에도 `format: youtube`면 동일 동작.
- 원고 길이는 `DG_YT_SCRIPT_MINUTES`(기본 10분, 분당 300자 환산).
- **남은 사용자 액션**: 유튜브 발제 1건으로 라이브 확인.

### 원고 수정·보완 핑퐁 오케스트레이터 쪽 완성 (2026-07-10, 브랜치 `claude/claude-md-telegram-pingpong-hfb443`)

yt_research 사이트가 만든 롱폼 원고(`vault/SNS 콘텐츠 제작 시스템/05 리뷰/대기/원고_*.md`)와
사용자의 텔레그램 답장을 잇는 핑퐁의 **오케스트레이터 쪽 나머지 절반**을 구현했다.
사이트 수신부(웹훅 → `_system/feedback/` pending 노트 저장)는 yt_research에 이미 있었다.
신규 모듈 `vault_pipeline/script_feedback.py` + 테스트 7종(전체 43종 통과).
- **① 초안 완성 알림**: `05 리뷰/대기`의 `type: youtube-script` + 검수 대기 원고를 찾아
  **파일명을 포함한** 텔레그램 메시지를 보낸다. 사용자가 이 메시지에 답장하면 사이트 웹훅이
  파일명을 추출해 피드백 노트를 만든다. 중복 알림은 `_system/logs/script_feedback_ledger.json`로 차단.
- **② 피드백 반영**: `_system/feedback/`의 `type: feedback, status: pending` 노트를 읽어 대상 원고를
  `llm.call_writing`(+`SCRIPT_REVISE` 프롬프트, HUMANIZE_RULES 주입)로 수정하고, 노트를
  `status: applied`(대상 없음/유실 의심 시 `error`)로 갱신 → 재처리 방지. 반영 완료를 텔레그램 통지.
- **안전장치**: 원고 수정은 **프론트매터 원문을 그대로 보존**하고 본문만 교체(끝에 HTML 주석 감사 흔적).
  수정본이 200자 미만이거나 원본의 50% 미만이면 내용 유실로 보고 반영하지 않고 `error`로 남긴다.
- **폴더/스키마 정합**: `VAULT_SCRIPT_PATH`(기본 `SNS 콘텐츠 제작 시스템/05 리뷰/대기`)·
  `VAULT_FEEDBACK_PATH`(기본 `_system/feedback`)를 사이트 lib/vault.ts와 동일 기본값으로 맞췄다.
- **배선**: `orchestrator.yml`(15분 cron)에 `python3 -m vault_pipeline.script_feedback` 단계 추가
  (기존 볼트 커밋·push 재시도 루프가 원고/피드백 변경도 함께 동기화). 수동 stage 실행 시엔 건너뜀.
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② yt_research가 원고를 저장하는 실제 폴더가 기본값과
  다르면 양쪽 `VAULT_SCRIPT_PATH`를 같은 값으로 맞출 것 ③ orchestrator Run workflow로 라이브 반영.

### 플라우드 파이프라인 "새 녹음 없음" 오판 수리 (2026-07-10, 브랜치 `claude/plaud-mcp-setup-6j07l1`)

텔레그램에 "처리할 새 녹음 없음"만 오던 원인 3개를 수리. vault_pipeline 테스트 20종 통과(신규 6종).
- **근본 원인**: 플라우드에서 **전사 안 된** 녹음은 `get_transcript`가 `[]`를 반환하는데, 이걸 유효
  전사로 취급 → "짧아서 생략"으로 장부에 **영구 기록**(18분짜리 포함 6건 소실, 산출물 0건이었음).
  `plaud_client._transcript_text()`가 응답에서 실제 발화만 추출, 빈 구조는 "전사 대기"로 분류해
  장부에 안 올림 → 앱에서 전사하면 다음 실행에 자동 처리.
- **기아 수정**: 전사 대기 녹음이 quota(`--max`)·fetch limit을 선점하지 않게 하고, todo를
  **오래된 것부터** 처리(최신 메모가 옛 녹음을 7일 창 밖으로 밀어내던 문제).
- **알림 정확화**: `telegram_notify.briefing(pending=)` — "⏳ 전사 대기 N건 — 앱에서 전사하면
  다음 실행에 자동 처리" 표시. 잘못된 장부 6건 리셋(ledger 비움).
- **운영 메모**: 이 파이프라인은 **플라우드 앱에서 전사가 돌아간 녹음만** 가공할 수 있다.
  자동 전사 설정을 켜두거나, 녹음 후 앱에서 전사를 실행해야 한다.
- **후속 수리 2건**: ① plaud-pipeline·vault-agents 워크플로우에 Claude Max CLI 폴백 배선
  (ANTHROPIC_API_KEY 시크릿이 비어 있어 FileNotFoundError('claude')로 전건 실패하던 것,
  orchestrator.yml 패턴 이식). ② 텔레그램 알림에 **녹음별 산출물 상세**(📼 녹음명 + 메모 제목
  최대 5개 + 🔑키워드 + 💬의견)와 저장 위치(`vault/제텔카스텐/{1.메모,2.키워드,3.의견}`) 표시 —
  `process_recording`이 `detail`을 반환, `briefing(details=)`가 렌더. 제목은 **GitHub 노트로
  열리는 링크**(텔레그램 HTML 모드, `note_url()` — blob/main URL). push 완료 후 링크가 열린다.

카드 저장소를 노션에서 완전히 걷어내고 옵시디언 볼트 하나로 고정, 동기화는 git/GitHub 단일 경로. 전체 27종 통과.
- **백엔드 일원화**: `state.py` 파사드를 옵시디언 전용으로(이중 백엔드·`DG_STATE_BACKEND` 폐기).
  `notion_state.py`·`notion_media.py` 삭제. 호출부 별칭 `notion_state`→`store`로 전 모듈 개명.
- **config**: `NOTION_*`·`require_notion` 제거. 저장소=볼트(`DG_VAULT_ROOT`), 알림=텔레그램.
- **워크플로우**: orchestrator·daily-intake·self-improve·backfill의 `NOTION_*` 시크릿 제거,
  볼트에 쓰는 워크플로우 전부에 **git 커밋·push 단계**(경합 재시도)와 `pyyaml`·`contents:write` 추가.
  test-cardnews의 노션 저장(`--notion-page`) 제거 → PNG 아티팩트만. cardnews의 노션 업로드 경로 삭제.
- **문서**: CLAUDE.md·ARCHITECTURE_V2·PLAUD_INTEGRATION·dreamgrow-resume·plaud-zettel의 노션 서술을
  볼트/Git로 교체. 통합기획 v3의 D-29(동기화=Obsidian Sync)를 **git/GitHub 유일**로 개정.
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② Actions Secrets에서 `NOTION_*` 삭제(선택) +
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` 설정 확인 ③ 진행 중이던 노션 카드가 있으면 볼트로 옮긴 뒤 실행.

### 오케스트레이터 안정성·토큰 수리 (2026-07-07, 브랜치 `claude/dreamgrow-orchestrator-review-z4zo4b`)

무개입 자동화를 깨던 "조용히 멈추는 구멍" 봉합 + 토큰 절감. 전체 테스트 25종 통과(신규 `orchestrator/test_run.py` 9종).
- **A1 수정 요청 데드엔드 해소**: `approval + revision_requested`를 처리하는 `handle_revision_requested`
  추가(DISPATCH 배선). 사람이 `📝 수정 요청` 섹션에 지시를 적고 `approval_status=revision_requested`로
  바꾸면 → keyword_approval로 되돌려 지시를 작가에게 되먹여 재초안(빈 키워드면 키워드 게이트로).
  `run_draft_dialogue(extra_directive=...)`로 첫 집필부터 반영.
- **A2 침묵 차단 해소**: `handle_final_approved`가 검수 미통과인데 승인된 경우 로그만 남기던 것을,
  `needs_human`+`approval_status=blocked`로 디큐하고 사유·다음 행동(재승인/재초안)을 `notify()`로 통지.
- **A3 실패 침묵 해소**: `run()`의 예외를 `_handle_failure`로 처리 — intake/research/keyword는 1회 자동
  재시도(`last_error`에 `[자동재시도]` 표식), 재시도 후에도 실패면 `failed`+통지. keyword_approval/approval은
  status 무시 쿼리라 표식으로 1회 재시도 후 `approval_status=failed`로 디큐. **publish_ready는 부분발행
  중복 위험으로 재시도 제외**(즉시 통지).
- **A4 고아 카드 청소기**: `run()` 시작 시 `_sweep_stale_running` — brief/draft가 running으로
  `DG_STALE_RUNNING_MINUTES`(기본 60) 넘게 멈추면 keyword_approval/approved로 재큐.
- **A5 스레드 글 유실 방지**: `split_posts`가 500자 초과 문단을 `[:500]`으로 잘라 버리던 것을
  문장 단위(`_split_sentences`) 이월 분할로 교체 — 글이 유실되지 않음.
- **A6 발행 성공 통지**: Threads/뉴스레터 발행 성공 시 링크와 함께 `notify()`(폰에서 사이클 종료).
- **B1 토큰**: `prompts._load_learned_overlay`에 `@lru_cache` — 카드당 10여 회 Honcho 원격 질의를 1회로.
- **B2 토큰**: 글 평가 총점이 `DG_RUBRIC_SKIP_QUALITY`(기본 45/50) 이상이면 2차안(전문 재작성) 생략.
- **모델 ID 고정(완료)**: `config.py`·`photo_judge.py` 기본 유틸리티 모델을 실재하지 않던
  `claude-sonnet-4-6` → **`claude-sonnet-5`**로 교체. (글쓰기는 `claude-opus-4-8` 유지)
- **B4 CLAUDE.md 대청소(완료)**: 상단을 옵시디언 전환 현행으로 교체, 개발 브랜치 갱신,
  과거 세션 로그(2026-06-13~07-06)를 `docs/HISTORY.md`로 이관(311→149줄).
- **A8 볼트 push 경합 방지**: orchestrator·plaud·vault-agents·cardnews-benchmark 워크플로우의
  `pull --rebase → push`를 5회 재시도 루프로 감싸 동시 push 실패(non-fast-forward)를 흡수.
- **B3 컨텍스트 선별 주입**: `read_sections_by_prefix`(두 백엔드+파사드) 추가. 키워드/브리프 단계에
  카드 본문 전체 대신 리서치·키워드 섹션만 주입 — A1 재초안 시 누적된 옛 초안 재주입을 막아 시너지.
- **B5 무거운 참고자료 첫 집필만**: 후킹·벤치마킹(13KB+)을 v1에만 넣고 비평/윤리 재작성 호출에선 제외.
  `get_style_context`에서 벤치마크 분리, `run_draft_dialogue(benchmark=...)`로 전달.
- **A7 완료(노션 철수 후)**: 학부모 발행 카드(`stage: published`) 원자 메모 환류를
  `vault_pipeline/feedback.py`에 추가(`find_published_pipeline`). 문체 학습은 발행 시 style_learn이
  이미 하므로 atomize만 수행(author 이한결·source_type own_content). 발행완료+본문 100자↑ 카드만,
  장부(feedback_ledger)로 중복 방지 — 잘못된 카드 유입 차단.
- **테스트**: 전체 30종 통과(신규 `test_run.py` 10종, `test_obsidian_state` B3 1종, `test_feedback` A7 3종).
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② orchestrator Run workflow로 라이브 반영.

> 지난 세션 기록은 `docs/HISTORY.md`로 이관했다 (2026-06-13 ~ 2026-07-06).

## 한국어 윤문 스킬 — 제3자 노출 문구는 무조건 적용 (필수)

제3자에게 보여주는 **모든 한국어 문구**를 작성·수정했다면, 발행·커밋 전에 반드시 아래 윤문 스킬을 거친다.
대상 예시: 스레드 글, 카드뉴스, 뉴스레터, 영상 스크립트, 강의 스크립트, 홈페이지·랜딩 카피라이팅,
앱 화면 텍스트(버튼·안내·오류 메시지 등 UI 문구), 상세페이지, SNS 게시물.
제외: 코드 주석, 내부 문서, 커밋 메시지 등 사용자 본인만 보는 텍스트.

- **기본**: `/im-not-strange-ai` — Sunny 문장 규칙 포함 (`.claude/skills/im-not-strange-ai`)
- **대안**: `/humanize-korean` 또는 `/humanize` (`.claude/skills/humanize-korean`)
- 8,000자 초과·정밀 검증이 필요하면 `--strict` (5인 파이프라인)
- 원칙: 의미·사실·수치는 한 글자도 바꾸지 않고 문체·리듬·표현만 다듬는다

스킬·에이전트는 이 저장소 `.claude/skills/`·`.claude/agents/`에 동봉되어 있다.
출처: https://github.com/epoko77-ai/im-not-ai · https://github.com/itssosunny/im-not-strange-ai

**자동 파이프라인에도 적용 (2026-07-01)**: GitHub Actions에서 도는 orchestrator는 Claude Code 스킬을
직접 못 쓰므로, 같은 룰북을 `prompts.py`의 `HUMANIZE_RULES` 상수로 요약해 작가(WRITER)·카드뉴스(CARDNEWS)
프롬프트에 주입했고, 비평가(CRITIC)에 "AI 티" 평가 기준(5번)을 추가해 토론 루프에서 탐지→재작성이 돌게 했다.
스레드·뉴스레터·카드뉴스 자동 초안 전부에 적용된다.
