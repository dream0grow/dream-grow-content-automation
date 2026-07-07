# 드림그로우 콘텐츠 자동화 — 프로젝트 컨텍스트

> 이 파일은 새 세션이 자동으로 읽는다. 작업을 이어가려면 `/dreamgrow-resume` 스킬을 호출하라.
> 지난 세션 기록(2026-06~07)은 `docs/HISTORY.md`에 있다.
> 마지막 갱신: 2026-07-07

## 무엇을 만들고 있나

초등 학부모 교육 브랜드 "드림그로우"의 콘텐츠를 **멀티 에이전트 파이프라인**으로 자동 생산·발행한다.
GitHub Actions가 cron으로 카드 저장소를 폴링하고, 사람은 모바일에서 카드 생성·승인만 한다.

흐름: `intake → 리서치 → 키워드 점수화 → ⏸️키워드 승인(자동승인 기본 ON) → 브리프 → 작가↔비평가↔검수 토론 초안 → 검수/평가 → ⏸️발행 승인 → 발행(Threads/스티비)`

**저장소 백엔드 전환 중** (`orchestrator/state.py` 파사드, 환경변수 `DG_STATE_BACKEND`):
- `notion`(현재 기본): 노션 DB — `orchestrator/notion_state.py`
- `obsidian`(전환 목표): `vault/파이프라인/` md 카드 + 텔레그램 알림 — `orchestrator/obsidian_state.py`
- 방향 확정(2026-07-06): 노션 → 옵시디언 중심 재구축, **노션 최종 철수**. 경위는 `docs/HISTORY.md`,
  이관 설계 `docs/기획/노션_옵시디언_이관설계.md`, 기준 사양 `docs/기획/통합기획_v3.md`.

상세 설계: `docs/ARCHITECTURE_V2.md`

## 핵심 ID / 리소스

- 개발 브랜치: **`claude/dreamgrow-orchestrator-review-z4zo4b`** (모든 작업은 여기서, main에 PR로 머지)
- 저장소: `dream0grow/dream-grow-content-automation`
- 노션 파이프라인 DB: `2581ffbe805540f68b4a472d07ae4197`
- 노션 데이터소스(카드 생성용): `74292f89-a5ca-4cfc-ba23-5d7b49059e7f`
- 노션 멘션 대상 user id(C-Box): `595b4d12-18aa-43a7-9aee-5ee84f3dc7ac`

## 코드 구조 (`orchestrator/`)

| 파일 | 역할 |
|---|---|
| `run.py` | stage 상태 머신 (DISPATCH) + 고아 청소·실패 재시도. cron이 `python3 -m orchestrator.run` 실행 |
| `state.py` | 저장소 파사드 — `DG_STATE_BACKEND`로 notion/obsidian 선택. 호출부는 이 모듈만 본다 |
| `notion_state.py` | 노션 DB 읽기/쓰기, 카드 본문 토글, KST 타임스탬프, 멘션 알림(`notify`) |
| `obsidian_state.py` | 옵시디언 백엔드 — `vault/파이프라인/` md 카드, 텔레그램+결재함 알림 |
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
- **초안 완성 시 노션 멘션 알림**: `handle_keyword_approved`가 발행 승인 게이트에서 `notify()` 호출.
  `NOTION_MENTION_USER_ID` 미설정 시 C-Box 기본 사용자로 폴백해 알림이 항상 뜬다.
- **매일 자동 발제**: `daily-intake.yml`이 하루 1회 `daily_intake.py` 실행 → 새 주제 카드 생성.
  개수는 `DG_DAILY_TOPIC_COUNT`(기본 1), 대상은 `DG_DEFAULT_AUDIENCE`(기본 "초등 저학년 학부모").

## 환경변수 / GitHub Secrets

필수: `NOTION_API_KEY`, `NOTION_PIPELINE_DB_ID`, (`ANTHROPIC_API_KEY` 또는 `CLAUDE_CODE_OAUTH_TOKEN`)
선택: `MANUS_API_KEY`, `HONCHO_API_KEY`, `NAVER_AD_API_KEY`/`NAVER_AD_SECRET`/`NAVER_AD_CUSTOMER_ID`,
`THREADS_ACCESS_TOKEN`/`THREADS_USER_ID`, `STIBEE_API_KEY`/`STIBEE_LIST_ID`/`STIBEE_SENDER_EMAIL`/`STIBEE_SENDER_NAME`/`STIBEE_AUTO_SEND`,
`NOTION_MENTION_USER_ID`(미설정 시 C-Box로 폴백), `DG_AUTO_APPROVE_KEYWORD`(기본 ON),
`DG_DAILY_TOPIC_COUNT`(기본 1), `DG_DEFAULT_AUDIENCE`(기본 "초등 저학년 학부모")

## 운영 — 자주 하는 작업

- **새 글 만들기**: 노션 DB에 카드 생성 (stage=intake, status=queued, format=thread/newsletter, audience 입력)
- **키워드 승인**: 키워드 표 확인 → `approved_keyword`에 키워드(또는 부모 고민 문장) 입력 + `approval_status=approved`
- **발행 승인**: 초안/검수 확인 → `review_status=approved`이면 `approval_status=approved` → 자동 발행
- **orchestrator 수동 실행**: GitHub Actions 탭 → orchestrator → Run workflow (Claude는 권한상 직접 실행 불가, 사용자가 클릭)
- **대량 검토 생성**: `DG_AUTO_APPROVE_KEYWORD=true` Secret → 키워드 자동 채택 → 초안까지 자동 (발행만 사람)

## 알아둘 제약

- Claude(이 세션)는 GitHub Actions 워크플로우를 **직접 실행 못 함**(403). 사용자가 Run workflow 클릭해야 함.
- 노션 카드 본문이 커서 `notion-fetch` 결과가 토큰 초과하면 파일로 저장됨 → python 슬라이스로 읽기.
- cron이 정시(00/30분)엔 자주 누락 → `8,23,38,53분`으로 설정함. 불안정하면 수동 실행.
- Manus listMessages는 structured output을 안 줌 → 25분 후 Claude 폴백이 정상 동작(품질 좋음).

## 현재 상태 (세션마다 갱신)

### 오케스트레이터 안정성·토큰 수리 (2026-07-07, 브랜치 `claude/dreamgrow-orchestrator-review-z4zo4b`) — ⬅️ 이번 세션 작업

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
  과거 세션 로그(2026-06-13~07-06)를 `docs/HISTORY.md`로 이관(311→약 145줄).
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
