# 프로젝트 맵 - dream-grow-content-automation

이 레포에서 동시에 진행 중인 작업 줄기와 파일 구성을 정리한 문서.

## 목표 3가지

1. **드림그로우 SNS 채널 자동화** - 콘텐츠 생성 → 검수 → 스케줄 → 발행 → 성과 추적
2. **로컬 PC 독립 실행** - PC가 꺼져도 핸드폰으로 계속 연동되는 구조 (진행 예정)
3. **병렬 에이전트 자가학습 팀** - 팀 에이전트 + diff 학습 + Honcho 메모리

## 작업 줄기별 파일 구성

### 1. 스레드(Threads) 콘텐츠 파이프라인 (핵심)

오케스트레이터: `pipeline.py` (generate → learn → publish → reels → leadmagnet)

| 단계 | 파일 |
|------|------|
| 생성 | `thread_generator.py` |
| 검수 | `content_reviewer.py` |
| 발행시간 배정 + 발행 계획 | `calendar_scheduler.py` (구 `publish_calendar.py` 통합) |
| 자동 발행 | `scheduled_publisher.py`, `threads_publisher.py` |
| 성과 수집 | `threads_insights.py` |

### 2. 릴스 / 유튜브 (Dream_Grow)

- `auto_reels_from_thread.py` - 스레드 → 릴스 변환 + 주제 직접 입력 모드 (구 `reels_script.py` 통합)
- `youtube_script.py` - Dream_Grow용 유튜브 스크립트 생성기

### 3. youtube/ 패키지 - **10x인생 프로젝트 소유 (수정 금지)**

`youtube/OWNERSHIP.md` 참조. Dream_Grow 세션은 이 폴더를 수정하지 않는다.
Semantic Scholar 리서치 → 롱폼 원고 → 제텔카스텐 적재 (자체 feedback_db 사용).

### 4. 리드마그넷 / 뉴스레터 / 이메일

- `lead_magnet_generator.py`, `lead_magnet_pdf.py` (→ `pdf_output/`)
- `newsletter_generator.py`, `maily_integration.py` (Maily 구독자/발송)

### 5. 자가학습 루프

- `diff_learner.py` - AI 초안 vs 사용자 수정본 비교 → 패턴 추출
- `memory_manager.py` - Honcho 메모리 (채널별 스타일 세션)
- `agents/skill-updater.md` - 학습 담당 에이전트 정의
- 참고: `youtube/feedback_db.py`는 10x인생 소유의 별도 로컬 JSON 학습 저장소 (통합 대상 아님)

### 6. 팀 에이전트 + 스케줄링

- `agents/team_runner.py` - 3개 팀(콘텐츠/지식/책) + skill-updater 순차 실행
- `scheduled/*.plist` - macOS launchd 스케줄 (로컬 PC 의존)

### 7. 지식 관리 (제텔카스텐 / 위키)

- `apple_notes_to_zettel.py` (+ `apple_notes_raw/` 원본 726건)
- `sync_wiki.py`, `rename_threads.sh`

### 8. 캘린더 / 일정 연동

- `calendar_sync.py` - 발행 캘린더 → Google Calendar
- `daily_planner.py` - 오늘 할 일 정리

### 공용 인프라

- `claude_client.py` - Claude Max 구독(CLI) 기반 LLM 호출 wrapper
- `main.py` - 대화형 통합 메뉴

## 통합 이력

- 2026-06: `publish_calendar.py` → `calendar_scheduler.py`로 통합 (`--weekly`, `--next`, `--month`)
- 2026-06: `reels_script.py` → `auto_reels_from_thread.py`로 통합 (`--topic` 모드)

## 알려진 갭 (목표 대비)

- **목표 2 (PC 독립 실행)**: 현재 모든 자동화가 로컬 Mac에 의존 - launchd 스케줄,
  `/Users/lhg/...` 하드코딩 경로(Obsidian/Dropbox), Claude CLI 로컬 인증.
  클라우드 실행(GitHub Actions, Claude Code on the web)으로 옮기려면 경로/저장소 추상화 필요.
- **목표 3 (병렬 에이전트)**: `team_runner.py`는 팀을 순차 실행. 병렬화 미구현.
