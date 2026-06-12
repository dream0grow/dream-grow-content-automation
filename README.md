# Dream Grow 콘텐츠 자동화

초등 자녀를 둔 부모를 위한 교육 콘텐츠(@dream_grow_lee)를 AI로 생성·검수·예약 발행하는 풀스택 웹 애플리케이션입니다.

```
AI 초안 생성 → 웹 에디터 리뷰/수정 → 검수 통과 → 발행 캘린더 예약 → Threads 자동 발행
                                                    ↘ 릴스 대본 / 뉴스레터 파생
```

## 아키텍처

| 계층 | 기술 | 설명 |
|------|------|------|
| 프론트엔드 | React 18 + Vite + TypeScript + Tailwind CSS v4 + TanStack Query | 대시보드 / 에디터 / 발행 캘린더 |
| 백엔드 | FastAPI + SQLAlchemy 2.0 + APScheduler | REST API + 60초 간격 예약 발행 스케줄러 |
| DB | SQLite (기본) / PostgreSQL (`DATABASE_URL` 교체) | 콘텐츠, 생성 잡, 발행 로그 |
| AI | Anthropic Claude API | 스레드 생성, 릴스/뉴스레터 파생 (`MOCK_LLM=true`로 키 없이 개발 가능) |
| 발행 | Meta Threads Graph API | 멀티포스트 스레드 발행 (토큰 없으면 자동 dry-run) |

## 빠른 시작 (개발)

```bash
# 백엔드 (자격증명 없이 mock 모드로 전체 기능 동작)
cd backend
pip install -r requirements.txt
MOCK_LLM=true PUBLISH_DRY_RUN=true uvicorn app.main:app --reload

# 프론트엔드 (별도 터미널, /api는 :8000으로 프록시)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

API 문서: http://localhost:8000/docs

## Docker 실행

```bash
cp .env.example .env   # 필요한 키 입력
docker compose up --build
# 앱: http://localhost:3000
```

PostgreSQL 사용 시:

```bash
docker compose --profile postgres up --build
# .env 또는 compose에서 DATABASE_URL=postgresql+psycopg://dreamgrow:dreamgrow@postgres:5432/dreamgrow
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | (없음) | Claude API 키. 없으면 mock 픽스처로 동작 |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | 생성에 사용할 모델 |
| `MOCK_LLM` | `false` | `true`면 고정 한국어 픽스처 반환 (오프라인 개발) |
| `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` | (없음) | Meta Threads API 자격증명. 없으면 자동 dry-run |
| `PUBLISH_DRY_RUN` | `true` | `true`면 실제 발행 없이 가짜 ID로 발행완료 처리 |
| `DATABASE_URL` | `sqlite:///./data/dreamgrow.db` | Postgres URL로 교체 가능 |
| `SCHEDULER_ENABLED` | `true` | 예약 발행 스케줄러 on/off |
| `CORS_ORIGINS` | `http://localhost:5173` | 개발용 CORS 허용 출처 (쉼표 구분) |

## 주요 API

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /api/generate/thread` | AI 스레드 생성 (202 + job_id, 폴링) |
| `GET /api/generate/jobs/{id}` | 생성 잡 상태 폴링 |
| `GET/POST/PUT/DELETE /api/contents` | 콘텐츠 CRUD |
| `POST /api/contents/{id}/status` | 상태 전이 (리뷰대기→리뷰완료→발행대기→발행완료) |
| `POST /api/contents/{id}/review` / `review/fix` | 규칙 검수 / 자동 수정 (이모지·금지 문구·글자 수) |
| `POST /api/contents/{id}/derive/reels` / `derive/newsletter` | 멀티채널 파생 |
| `GET /api/calendar?start=&end=` | 기간별 발행 캘린더 |
| `POST /api/calendar/auto-schedule` | 카테고리 균형 자동 슬롯 배정 (preview 지원) |
| `POST /api/contents/{id}/publish` | 즉시 발행 |
| `GET /api/system/status` | 스케줄러/설정 상태 |

## 도메인 규칙

- 상태 흐름: `리뷰대기 → 리뷰완료 → 발행대기 → 발행완료` (검수 ERROR 시 리뷰완료 차단, `force` 가능)
- 발행 슬롯: 매일 07:10 / 17:50 / 20:50 KST, 하루 최대 3개
- 자동 배정: 같은 날·연일 동일 카테고리 회피
- 검수 규칙: 이모지 금지(자동 제거), 출처 없는 % 수치 경고, 금지 마무리 문구, 브랜드 서명(`아이와 부모의 꿈을 키웁니다. -Dream_Grow-`), 포스트당 500자(Threads 제한)/280자(권장)
- 자동 수정에는 한글 손실 가드 적용 (치환 후 한글이 80% 미만으로 줄면 무효화)

## 테스트

```bash
cd backend && python3 -m pytest tests/ -v
```

splitter(포스트 분할), reviewer(검수 규칙), contents API(상태 전이), scheduler(슬롯 배정), publish flow(dry-run/모킹된 Threads API) 전부 오프라인으로 실행됩니다.

## 프로젝트 구조

```
backend/
  app/
    core/        설정(config), 도메인 상수(constants)
    db/          SQLAlchemy 엔진/모델
    schemas/     Pydantic 요청/응답 스키마
    routers/     contents, generation, calendar, publish, system
    services/    llm, generator(프롬프트), reviewer, publisher, splitter, scheduler_svc
    jobs/        APScheduler 예약 발행 잡
  tests/
frontend/
  src/
    api/         fetch 클라이언트, 타입, TanStack Query 훅
    pages/       Dashboard, Editor, Calendar
    components/  GenerateModal, ThreadPostPreview, ReviewChecklist 등
    lib/         threadSplit(백엔드와 동일 분할 로직), dates
```

## 레거시 스크립트

저장소 루트의 Python 스크립트들(`thread_generator.py`, `threads_publisher.py` 등)은 Obsidian 볼트 + launchd 기반의 기존 CLI 워크플로우입니다. 웹 앱은 이들의 프롬프트·검수 규칙·발행 로직을 `backend/app/services/`로 포팅했으며, 레거시 스크립트는 기존 환경(macOS)에서 그대로 사용할 수 있습니다.

## 향후 확장 포인트

- Honcho 메모리 학습: `generator.generate_thread(..., extra_context=)` 훅에 주입
- 성과 인사이트 대시보드: `threads_insights.py` 로직 포팅
- Alembic 마이그레이션: 모델이 안정되면 `create_all` 대체
