# 드림그로우 자동화 v2 — 노션 중심 멀티 에이전트 오케스트레이션

작성일: 2026-06-12

## 0. 확정된 설계 결정 (6가지)

| # | 결정 | 구현 방식 |
|---|---|---|
| 1 | 상태 저장소는 **노션** | `콘텐츠 파이프라인` DB 하나가 단일 진실 공급원. stage/status 변경이 곧 트리거 |
| 2 | **기존 시스템 통합** | claude_client, memory_manager(Honcho), diff_learner를 그대로 재사용. 신규 코드는 `orchestrator/`에만 추가 |
| 3 | **Manus는 외부 리서치 전담** | `task.create`는 리서치 stage에서만 호출. 키 미설정 시 Claude 리서치로 폴백 |
| 4 | **핸드폰 연속성 + 24시간 가동** | GitHub Actions cron이 30분마다 노션 DB를 폴링. 운영자는 노션 모바일 앱에서 카드 생성·승인만 하면 됨 (Mac 불필요) |
| 5 | **병렬 에이전트 간 대화** | 작가↔비평가↔교육윤리 검수자가 제한된 라운드(기본 2회)로 토론하며 초안을 업그레이드. 전체 대화록은 노션 페이지에 기록 |
| 6 | **자가 학습 (헤르메스 스타일)** | 주간 회고 에이전트가 Honcho 수정 패턴 + 성과 데이터를 분석해 프롬프트 개선안을 **큐시트**(승인 대기 카드)로 제출. 사람 승인 후에만 반영 |

## 1. 전체 구조

```text
[운영자: 노션 모바일/데스크톱]
   │  카드 생성 (주제 입력) · 승인 (approval_status 변경)
   ▼
[노션 DB: 콘텐츠 파이프라인]  ← 단일 진실 공급원
   │  stage / status / approval_status
   ▼
[GitHub Actions cron (30분)] → python3 -m orchestrator.run
   │
   ├─ intake      → Manus 리서치 3종 병렬 생성 (학술/부모언어/트렌드)
   ├─ research    → Manus 완료 폴링 → 리서치 요약 노션 저장
   ├─ keyword     → Claude 키워드 점수화 (근거·브랜드핏·확장성·시급성)
   │                 → keyword_approval, needs_human  ⏸️ 사람 승인
   ├─ brief       → Claude 브리프 1개 생성
   ├─ draft       → 에이전트 토론 루프 (작가↔비평가↔윤리검수) → 초안
   ├─ review      → 기계 검수 + 맥락 검수 → approval, needs_human  ⏸️ 사람 승인
   └─ approval    → publish_ready (발행은 기존 threads_publisher가 로컬에서 수행)

[GitHub Actions cron (주 1회)] → python3 -m orchestrator.self_improve
   └─ Honcho 수정 패턴 + 성과 분석 → 프롬프트 개선 큐시트 제출 ⏸️ 사람 승인
```

노션 AI 오케스트레이션 3.0의 어휘로 보면:
- **지침/룰북** → `orchestrator/prompts.py`의 브랜드 보이스·절대규칙 (모든 호출에 주입)
- **에이전트** → 리서치·키워드·브리프·작가·비평가·윤리검수·회고 페르소나
- **프로토콜** → `orchestrator/run.py`의 stage 상태 머신
- **큐시트 (Level 2 승인)** → `needs_human` 상태 카드. 승인 없이는 다음 stage로 못 감
- **Level 1 (즉시 실행)** → 리서치, 점수화, 초안 생성

## 2. 핵심 운영 원칙

1. 에이전트 간 대화는 **라운드 제한(기본 2)** 안에서만 허용하고, 전 과정을 노션 페이지에 기록한다. 끝없는 자유 대화 금지.
2. 모든 작업은 `content_id` 기준. `idempotency_key`(content_id:stage)로 중복 실행 방지.
3. `review_status=approved` AND `approval_status=approved` 없이는 publish_ready로 못 간다.
4. 자가 학습은 제안까지만 자동. **프롬프트 실제 변경은 사람 승인 후** 적용.
5. API 키는 GitHub Secrets / .env에만. 노션·로그에 기록 금지.

## 3. 노션 DB 스키마 (콘텐츠 파이프라인)

| 속성 | 타입 | 값 |
|---|---|---|
| 이름 | title | 주제 |
| content_id | rich_text | DG-2026-0001 (비면 자동 발급) |
| stage | select | intake, research, keyword, keyword_approval, brief, draft, review, approval, publish_ready, published, analysis |
| status | select | queued, running, needs_human, approved, revise, failed, done |
| audience | rich_text | 초등 저학년 부모 등 |
| format | multi_select | thread, reels, newsletter, blog |
| priority | select | P0, P1, P2 |
| approval_status | select | not_requested, requested, approved, revision_requested, rejected |
| review_status | select | not_started, approved, revise, hold |
| approved_keyword | rich_text | 승인된 키워드 (사람이 입력) |
| manus_task_ids | rich_text | 쉼표 구분 task id |
| published_url | url | 발행 링크 |
| idempotency_key | rich_text | 중복 실행 방지 |
| last_error | rich_text | 최근 오류 |

리서치 요약·키워드 표·브리프·초안·검수 결과·에이전트 대화록은 카드 **페이지 본문**에 단계별 토글 블록으로 누적된다.

## 4. 핸드폰 운영 시나리오

1. 출근길에 노션 모바일에서 새 카드 생성: 제목에 주제, audience 입력, stage=intake, status=queued
2. 30분 내 GitHub Actions가 감지 → 리서치 → 키워드 점수화까지 자동 진행
3. 점심에 알림 확인(노션 알림): keyword_approval 카드에서 키워드 표 확인 → `approved_keyword`에 선택 키워드 입력 + approval_status=approved
4. 오후에 초안 완성 + 검수 결과가 카드에 쌓임 → 승인하면 publish_ready
5. 발행은 기존 파이프라인(threads_publisher) 또는 추후 cloud 발행 모듈이 수행

## 5. 자가 학습 루프 (헤르메스 스타일)

```text
[데이터 수집] Honcho corrections + team_learnings + 노션 published 카드의 metrics
      ▼
[회고 에이전트] 반복 수정 패턴 / 고성과 패턴 / 프롬프트 결함 진단
      ▼
[큐시트 제출] 노션에 "프롬프트 개선안 vN" 카드 생성 (변경 전→후 diff 포함, needs_human)
      ▼
[사람 승인] approval_status=approved
      ▼
[적용] 다음 실행에서 orchestrator가 개선안을 prompts 오버레이로 로드 + Honcho에 승격 저장
```

기존 `diff_learner`(사용자 수정 학습)와 `skill-updater`(패턴 승격)가 이미 이 루프의 절반을 수행한다. v2는 여기에 ① 성과 데이터 결합, ② 프롬프트 자체의 자동 개선 제안, ③ 승인 게이트를 추가한 것이다.

## 6. 생성된 노션 DB

- **드림그로우 콘텐츠 파이프라인**: https://app.notion.com/p/2581ffbe805540f68b4a472d07ae4197
- `NOTION_PIPELINE_DB_ID` = `2581ffbe805540f68b4a472d07ae4197`
- ⚠️ 노션에서 내부 integration을 만들고(https://www.notion.so/my-integrations),
  이 DB 페이지의 `⋯ → 연결(Connections)`에서 해당 integration을 추가해야 REST API 접근이 가능하다.

## 7. 환경 변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `NOTION_API_KEY` | ✅ | 노션 내부 integration 토큰 |
| `NOTION_PIPELINE_DB_ID` | ✅ | 콘텐츠 파이프라인 DB id |
| `ANTHROPIC_API_KEY` | 둘 중 하나 | API 종량제 키. 없으면 아래 토큰으로 폴백 |
| `CLAUDE_CODE_OAUTH_TOKEN` | 둘 중 하나 | Claude Max 구독 토큰. Mac에서 `claude setup-token`으로 발급 (1년 유효) |
| `MANUS_API_KEY` | 선택 | 미설정 시 리서치도 Claude가 수행 |
| `HONCHO_API_KEY` | 선택 | 문체/학습 메모리 |
| `THREADS_ACCESS_TOKEN` | 선택 | Threads 자동 발행용. 미설정 시 수동 발행 안내로 폴백 |
| `THREADS_USER_ID` | 선택 | Threads 사용자 ID |
| `DG_MODEL_UTILITY` | 선택 | 기본 claude-sonnet-4-6 |
| `DG_MODEL_WRITING` | 선택 | 기본 claude-opus-4-8 |

GitHub Actions에서는 위 키들을 repo Secrets로 등록한다.

## 8. 마이그레이션 로드맵

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 노션 DB 생성 + orchestrator 모듈 + Actions cron | 본 브랜치에서 구현 |
| 2 | 발행 자동화: publish_ready 카드를 orchestrator/publish.py가 Threads API로 직접 발행 (클라우드, Mac 불필요) | 구현됨 |
| 3 | 성과 자동 수집 (Threads insights → 노션 metrics) | 다음 |
| 4 | 자가 학습 큐시트 승인 → 프롬프트 파일 자동 갱신 PR | 다음 |
