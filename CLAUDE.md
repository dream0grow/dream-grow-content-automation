# 드림그로우 콘텐츠 자동화 — 프로젝트 컨텍스트

> 이 파일은 새 세션이 자동으로 읽는다. 작업을 이어가려면 `/dreamgrow-resume` 스킬을 호출하라.
> 마지막 갱신: 2026-06-13

## 무엇을 만들고 있나

초등 학부모 교육 브랜드 "드림그로우"의 콘텐츠를 **노션 중심 멀티 에이전트 파이프라인**으로 자동 생산·발행한다.
GitHub Actions가 30분마다 노션 DB를 폴링하며, 사람은 노션 모바일 앱에서 카드 생성·승인만 한다.

흐름: `intake → 리서치 → 키워드 점수화 → ⏸️키워드 승인 → 브리프 → 작가↔비평가 토론 초안 → 검수/평가 → ⏸️발행 승인 → 발행(Threads/스티비)`

상세 설계: `docs/ARCHITECTURE_V2.md`

## 핵심 ID / 리소스

- 개발 브랜치: **`claude/fervent-bell-0iwlia`** (모든 작업은 여기서, main에 PR로 머지)
- 저장소: `dream0grow/dream-grow-content-automation`
- 노션 파이프라인 DB: `2581ffbe805540f68b4a472d07ae4197`
- 노션 데이터소스(카드 생성용): `74292f89-a5ca-4cfc-ba23-5d7b49059e7f`
- 노션 멘션 대상 user id(C-Box): `595b4d12-18aa-43a7-9aee-5ee84f3dc7ac`

## 코드 구조 (`orchestrator/`)

| 파일 | 역할 |
|---|---|
| `run.py` | stage 상태 머신 (DISPATCH). cron이 `python3 -m orchestrator.run` 실행 |
| `notion_state.py` | 노션 DB 읽기/쓰기, 카드 본문 토글, KST 타임스탬프, 멘션 알림(`notify`) |
| `prompts.py` | 브랜드 보이스/룰북 + 에이전트 프롬프트 (리서치/키워드/브리프/작가/비평가/검수/평가/회고) |
| `agent_dialogue.py` | 작가↔비평가↔검수 토론 루프 + 벤치마킹/후킹 로드 |
| `manus_research.py` | Manus 외부 리서치(전담). 25분 내 결과 없으면 Claude 폴백 |
| `naver_keywords.py` | 네이버 검색광고 API로 키워드 실측 검색량/경쟁도 |
| `publish.py` | publish_ready 카드 발행 (Threads 체인 / 스티비 뉴스레터) |
| `stibee.py` | 스티비 3단계 발행: POST /emails → POST /emails/{id}/content(text/html) → /send |
| `style_learn.py` | AI 원본 vs 사람 수정본 diff → Honcho 문체 학습 |
| `self_improve.py` | 주간 회고 → 프롬프트 개선 큐시트(사람 승인 후 반영) |
| `config.py` | 환경변수 한 곳 관리 |

데이터: `data/benchmark_posts.md`(스레드 7구조·12훅·변주, CSV 분석), `data/hook_patterns.md`(후킹 패턴).
워크플로우: `.github/workflows/orchestrator.yml`(30분 cron), `self-improve.yml`(주간), `test-stibee.yml`(수동 발송 테스트).

## 환경변수 / GitHub Secrets

필수: `NOTION_API_KEY`, `NOTION_PIPELINE_DB_ID`, (`ANTHROPIC_API_KEY` 또는 `CLAUDE_CODE_OAUTH_TOKEN`)
선택: `MANUS_API_KEY`, `HONCHO_API_KEY`, `NAVER_AD_API_KEY`/`NAVER_AD_SECRET`/`NAVER_AD_CUSTOMER_ID`,
`THREADS_ACCESS_TOKEN`/`THREADS_USER_ID`, `STIBEE_API_KEY`/`STIBEE_LIST_ID`/`STIBEE_SENDER_EMAIL`/`STIBEE_SENDER_NAME`/`STIBEE_AUTO_SEND`,
`NOTION_MENTION_USER_ID`, `DG_AUTO_APPROVE_KEYWORD`

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

- 시스템 완성: 리서치~키워드~브리프~토론초안~검수~발행(Threads/스티비) 전부 작동. **스티비 실제 발송 성공 확인**.
- 핸드오프 시스템 가동: CLAUDE.md + `/dreamgrow-resume` 스킬 (PR #18 머지됨).
- **Manus 429 백오프 추가 (2026-06-13, PR #19로 main 머지 완료 — HEAD `9247caa`)**: 카드 대량 처리 시 `task.create`
  버스트가 Manus 레이트리밋(429)에 걸려 research 단계에서 8개가 일괄 실패했었음. `manus_research.py`에
  `_request_with_retry`(429/5xx 지수 백오프 2→4→8→16초, Retry-After 존중) + task.create 사이 1초 간격을 추가해 완화.
  환경변수 `DG_MANUS_MAX_RETRIES`(기본 4)로 조절. **머지 후 사용자가 orchestrator를 Run workflow로 재실행해야 효과 발생**
  (cron은 main에서 도는데, 머지 전 11:19 수동 실행은 옛 코드라 8개가 또 429 실패했을 수 있음 → 재실행 필요).
- **노션 카드 현황** (2026-06-13 갱신):
  - DG-2026-0001 (스마트폰 규칙): publish_ready, review·approval 모두 approved → 다음 orchestrator 실행 시 Threads 자동 발행
  - DG-2026-0002 (친구 문제): 키워드 승인 완료(approval_status=approved 처리함) → 다음 실행에 브리프→초안 진행
  - 받아쓰기/형제비교/칭찬함정: research running (Manus task 진행 중)
  - 발표목소리/거짓말: intake 대기
  - 429로 실패했던 8개(수학포기/자존감/책읽기/구구단/우는아이/1학년학교/화내고후회/심심해): stage=intake, status=queued로
    리셋 완료 (idempotency_key·last_error 비움) → 다음 실행에 재시도. content_id는 유지됨.
    (8번 1학년학교·10번 형제비교는 유지하기로 함 — 삭제 안 함)
- **다음 자동 진행 대기**: `DG_AUTO_APPROVE_KEYWORD=true` Secret이 켜져 있으면, orchestrator를 2~3회 실행 시
  검토용 카드들이 키워드 자동 채택 → 브리프 → 초안 → 검수까지 진행되어 "발행 승인 대기"로 모인다.
  (Claude는 Actions를 직접 실행 못 하므로 사용자가 Run workflow 클릭 필요)

### 뉴스레터 자동화 검토 결과 (2026-06-14) — ⬇️ 다음 세션 이어받을 작업

경로는 견고함: `format=newsletter` → 토론초안(16k토큰·3000~6000자) → `✍️ 초안 (newsletter)` →
`publish.py._publish_newsletter` → `stibee.create_and_send`(이메일생성→HTML주입→AUTO_SEND면 발송). 실발송 성공 이력 있음.
검토에서 발견한 갭과 **사용자가 승인한 다음 할 일**:

- **[구현 완료, 2026-06-14] 코드 수정 #1·#2·#4** (브랜치 `claude/vigilant-shannon-mcrpao`, PR 머지 대기):
  - #1 (`publish.py`): newsletter **단독** 카드가 발송 성공해도 `published`로 안 넘어가던 문제 해결. ✅
    `_publish_newsletter`가 실발송 성공 시 `True`(stibee `sent` 기반) 반환 → thread 없는 카드는 sent=True면
    `stage=published, status=done`, 아니면 needs_human.
  - #2 (`stibee.py` `markdown_to_html`): 리스트(`- `/`* `)·링크(`[t](url)`)가 평문으로 나오던 문제 해결. ✅
    `_inline()` 헬퍼(볼드+링크) + `<ul><li>` 변환 추가. 로컬 렌더 테스트 통과.
  - #4 (`run.py`): 발행 승인 안내 문구의 "Maily 붙여넣기" 옛 표현을 스티비 자동 발행 문구로 교정. ✅
  - (#3 제목 중복은 이번 범위 제외 — 사용자가 #1·#2·#4만 선택.)
  - **남은 사용자 액션**: 이 브랜치를 PR로 main에 머지.
- **[사용자 액션] test-stibee로 실발송 검증**: GitHub Actions → `test-stibee` → Run workflow
  (테스트 주소록에 실제 1통 발송, `STIBEE_AUTO_SEND=true` 강제). Claude는 직접 실행 불가.

### 평가표 내장 + 2차안 자동화 (2026-06-16, 브랜치 `claude/vigilant-shannon-mcrpao`)

- **평가표**: `data/thread_rubric.md`(사용자 글 CSV=benchmark_posts.md 기준, 100점=문체40/구조30/논리성30).
  핵심 약점은 **줄 길이**(스레드는 한 줄 의미 단위 15~18자, `<br>`/Enter).
- **파이프라인 내장(구현 완료)**:
  - `prompts.py`: WRITER(thread)에 줄바꿈 규칙 주입 + `LINE_BREAK_RULE` + `RUBRIC_REVIEW` 프롬프트.
  - `rubric_review.py`(신규): 초안 채점 → `📐 평가표 점검` + `✍️ 2차안 (fmt)` 토글 기록(idempotent).
  - `run.py`: 초안 단계에서 자동 생성 + `--stage rubric_backfill`(기존 카드 소급).
  - `.github/workflows/backfill-2cha.yml`: 수동 실행으로 기존 모든 카드 일괄 2차안.
- **남은 사용자 액션**: ① 이 브랜치 main 머지(라이브 파이프라인=main에서 동작) ② `backfill-2cha`
  Run workflow로 기존 카드에 2차안 일괄 생성(Claude는 Actions 실행 불가, 403).
- **왜 노션에 글이 자동으로 안 쌓이나(진단)**: ① cron이 GitHub에 의해 대폭 누락(설정 15분, 실제 수 시간 간격).
  ② 기존 카드는 전부 `status=needs_human`(발행 승인 대기)에서 멈춤 — 자동화는 끝났고 사람 승인 대기.
  ③ 새 카드는 사람만 생성 → 새 글 자체가 안 늘어남. 결론: 막힌 게 아니라 승인 게이트에 모여 있음.

