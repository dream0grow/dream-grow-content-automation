# 드림그로우 콘텐츠 자동화 — 프로젝트 컨텍스트

> 새 세션이 자동으로 읽는 파일. 작업을 이어가려면 `/dreamgrow-resume` 호출.
> 과거 세션의 상세 기록은 `docs/HISTORY.md`, 단일 기획 사양서는 `docs/기획/통합기획_v3.md`.
> 마지막 갱신: 2026-07-07

## 무엇을 만들고 있나 — "사람은 승인만 하는" 콘텐츠 에이전트 OS

두 파이프라인이 GitHub Actions에서 돌고, 산출물은 옵시디언 볼트(`vault/` = 초생산)에 쌓인다:

1. **학부모 파이프라인 (드림그로우)**: 카드 상태 머신 —
   `intake → 리서치(Manus/Claude) → 키워드(자동승인) → 브리프 → 작가↔비평가 토론 초안
   → 윤리검수(되먹임) → ⏸️발행 승인 → Threads/스티비 발행 → 문체 학습`
2. **교사그룹 파이프라인 (교육운동: 꿈들·새넷·전교조)**: 플라우드 녹음 →
   ①사례은행(신호등) ②제텔카스텐 1.메모→2.키워드→3.의견 ③블로그·페북 초안(발행은 사람)
   → 발행완료 시 문체 학습 + 원자 메모 환류

**옵시디언 전환 중 (노션 철수 예정)**: 카드 저장소는 `orchestrator/state.py` 파사드가
Actions Variable `DG_STATE_BACKEND`(기본 notion, `obsidian`이면 볼트 `vault/파이프라인/`)으로
스위치. 노션 잔여 카드 이전(M2) 후 노션 구독 해지 — 절차: `docs/기획/노션_옵시디언_이관설계.md`.

## 핵심 ID / 리소스

- 저장소: `dream0grow/dream-grow-content-automation` (코드+볼트 단일 저장소, main이 라이브)
- 볼트: `vault/` — 헌법은 `vault/CLAUDE.md` (쓰기 권한 매트릭스, `_ai` 딱지, 사례 신호등, 타겟 분리)
- 노션 파이프라인 DB: `2581ffbe805540f68b4a472d07ae4197` (이관 완료 시까지만)
- 발행 대시보드: `dashboard/index.html` (GitHub API 직결, fine-grained PAT 로그인)
- 텔레그램: 알림 서버리스(`vault_pipeline/telegram_notify.py`), Secrets `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`

## 코드 지도

| 영역 | 내용 |
|---|---|
| `orchestrator/run.py` | 카드 상태 머신(DISPATCH) + 고아·실패 카드 청소기(sweep). 15분 크론 |
| `orchestrator/state.py` | 카드 저장소 파사드 (notion_state ↔ obsidian_state) |
| `orchestrator/agent_dialogue.py` | 작가↔비평가 토론 + 윤리검수 되먹임 루프(ETHICS_MAX_ROUNDS) |
| `orchestrator/publish.py` | Threads 체인/스티비 발행 + 발행 전 문체 학습(style_learn) + 성공/실패 알림 |
| `orchestrator/prompts.py` | 브랜드 보이스·룰북·HUMANIZE_RULES + 전 에이전트 프롬프트 |
| `orchestrator/` 기타 | manus_research(폴백·429백오프)·naver_keywords·rubric_review(평가표+2차안)·daily_intake·cardnews·stibee·self_improve·style_learn(Honcho) |
| `vault_pipeline/` | 플라우드→볼트: run(triage)·writers·feedback(문체 학습+메모 분해)·socrates(새벽 질문)·telegram_notify·plaud_client(MCP stdio+인박스) |
| `tools/` | vault_secret_scan(커밋 게이트)·vault_migrate(볼트 이관)·naver_blog_scrape(문체 벤치마크) |
| `.claude/agents/zk-*` | 지식팀 서브에이전트 8종 (v3 §5) |
| 문체 원천 | `vault/raw/스레드_아카이브/`(CSV 2,068편+TOP30)·`raw/블로그글`·`raw/페이스북글`·`raw/스레드_정답글` + `_system/style_lessons.md`(수정 학습 누적) |

워크플로우: `orchestrator.yml`(15분) · `daily-intake.yml`(매일 발제) · `plaud-pipeline.yml`(KST 22:08,
되먹임 포함) · `vault-agents.yml`(socrates, KST 05:08) · `weekly-snapshot.yml`(복구 태그) ·
`self-improve.yml` · `test-stibee.yml` · `test-cardnews.yml` · `backfill-2cha.yml`

## 환경변수 / GitHub Secrets

필수: `ANTHROPIC_API_KEY` (+이관 전 `NOTION_API_KEY`·`NOTION_PIPELINE_DB_ID`)
선택: `MANUS_API_KEY`, `HONCHO_API_KEY`, `THREADS_ACCESS_TOKEN`/`THREADS_USER_ID`,
`STIBEE_*`, `NAVER_AD_*`, `PLAUD_TOKENS_JSON`(캐시로 자동 갱신), `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`,
`DG_AUTO_APPROVE_KEYWORD`(기본 ON), `DG_DAILY_TOPIC_COUNT`(기본 1)
Variables: `DG_STATE_BACKEND`(notion|obsidian)

## 운영 — 사람이 하는 일 (이것뿐)

- **발행 승인**: 대시보드/옵시디언에서 초안 확인·수정 → `approval_status=approved` → 자동 발행
- **AI에게 수정 시키기**: 카드에 `🛠 수정 지시` 섹션을 만들어 지시 작성 +
  `approval_status=revision_requested` → 다음 실행이 재작성 후 재승인 요청
- **교사 글 발행**: `프로젝트/교육운동/*_초안` 복붙 발행 → `상태: 발행완료` (문체 학습+메모 환류 자동)
- **노랑 사례 결재**: `_system/review_queue.md` 체크
- **소크라테스 답하기**: `_system/dialogues/오늘.md`에 직관 한 줄+답 (→ 의견 노트 원석)
- **수동 실행**: Actions 탭 → Run workflow (Claude는 403이라 직접 실행 불가)

## 알아둘 제약·원칙

- 실패·차단·승인 대기는 반드시 알림(notify)이 가야 한다 — **조용한 정체 금지** (2026-07-07 감사로 봉합)
- 사례·의견·주장은 AI가 창작하지 않는다. 재료 없으면 사례 생략(자리 표시도 금지)
- cron 정시는 누락 잦음 → 8분 오프셋 사용. Manus 무응답 25분 → Claude 폴백
- 볼트 동기화는 git 하나 (Obsidian Git). 공식 Sync 병행 금지
- 노션 카드 본문이 크면 notion-fetch가 파일 저장 → 파이썬 슬라이스로 읽기

## 현재 상태 (세션마다 갱신 — 상세는 docs/HISTORY.md)

### 오케스트레이터 감사·수리 (2026-07-07, 브랜치 `claude/content-automation-obsidian-mtsmj6`) — ⬅️ 최신

"거의 신경 안 쓰는 자동화" 기준 감사에서 찾은 침묵 구멍 5곳 + 토큰 낭비 5건을 수리:
- **A1** `revision_requested` 핸들러 신설 — 수정 지시(`🛠 수정 지시` 섹션)대로 재작성→재승인 요청
- **A2** 승인 후 검수 차단 시 조용히 멈추던 것 → needs_human 전환+사유·선택지 통지
- **A3** 실패 카드 1회 자동 재시도(sweep, RETRY_MARK)·재실패 시 알림
- **A4** brief/draft running 60분 초과 고아 카드 자동 재큐
- **A5** Threads 장문 문단 잘림 → 문장 단위 이월 분할 / **A6** 발행 성공·실패 모두 폰 통지
- **A7** 발행된 파이프라인 카드도 원자 메모 환류 / **A8** 볼트 push 3회 재시도
- **B1** Honcho 오버레이 lru_cache(호출당→프로세스당 1회) / **B2** QUALITY_SCORE 제거(평가표로 일원화,
  88점 이상이면 2차안 생략) / **B3** 키워드·브리프 컨텍스트를 섹션 선별(read_sections_by_prefix)로
  / **B5** 재작성 호출의 벤치마크 절반 / **B4** CLAUDE.md 26KB→9KB, 과거 기록 docs/HISTORY.md 이관
- 참고: 윤리 되먹임 루프는 PR #30으로 이미 main에 있음 (HISTORY의 "PR 미생성" 기록은 낡은 것)

### 직전 세션 요약 (2026-07-06, 상세는 HISTORY)
옵시디언 중심 재구축 확정(노션 철수 예정) · 볼트 v3 골격+이관도구 · 플라우드 3종(사례은행/제텔카스텐/교사 초안,
테스트 통과) · 문체 학습 루프+원소스 멀티유즈 · 텔레그램 알림 · 발행 대시보드 · 노션 이관 M0~M1(백엔드 스위치) ·
에이전트 OS 1차(zk-8종+socrates 새벽 잡) · 유출 키 재발급 완료

### 남은 사용자 액션
① `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID` Secrets 등록 ② Obsidian Git 연동+기존 볼트 이관
(`docs/OBSIDIAN_SETUP.md`) ③ 맥에서 `tools/naver_blog_scrape.py l0126j` 실행 ④ 정답 스레드 글을
`raw/스레드_정답글`에 투입 ⑤ 다음 세션: 노션 카드 이전(M2)→`DG_STATE_BACKEND=obsidian`→노션 해지,
음성 수정 루프, 본인 글 분석으로 values·채널별 문체 가이드

## 한국어 윤문 스킬 — 제3자 노출 문구는 무조건 적용 (필수)

제3자에게 보여주는 **모든 한국어 문구**(스레드·카드뉴스·뉴스레터·스크립트·UI 문구·SNS 게시물)를
작성·수정했다면 발행·커밋 전에 윤문 스킬을 거친다. 코드 주석·내부 문서·커밋 메시지는 제외.

- 기본 `/im-not-strange-ai`, 대안 `/humanize-korean`. 8,000자 초과·정밀 검증은 `--strict`
- 원칙: 의미·사실·수치는 한 글자도 바꾸지 않고 문체·리듬·표현만 다듬는다
- 자동 파이프라인은 같은 룰북을 `prompts.HUMANIZE_RULES`로 주입받는다 (스레드·뉴스레터·카드뉴스·교사 글 전부)
