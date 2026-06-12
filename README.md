# Dream Grow Content Studio

콘텐츠 자동화 시스템을 셀프호스트 가능한 풀스택 웹 앱으로 재구축한 MVP입니다.
기존 Python CLI 스크립트(`legacy/`)의 도메인 로직(스레드 생성기, Threads 발행기,
검수 규칙, Honcho 메모리)은 보존하되, Obsidian 파일 의존을 제거하고 DB·웹 UI·
비동기 잡 큐 위에 재구성했습니다.

## 아키텍처

```
Next.js 14 (App Router, TypeScript, Tailwind)
        │  REST + SSE
        ▼
FastAPI (uvicorn) ─── PostgreSQL 16
        │                ▲
        └─ Redis ◄──┐    │ SQLAlchemy 2.0 async + Alembic
                    │    │
              Celery 워커 + Beat
                    │
   ┌────────────────┼─────────────────┐
   ▼                ▼                 ▼
Anthropic     Meta Threads        Maily.so
(생성)        (발행 + 인사이트)   (뉴스레터)
```

자세한 설계 근거는 [`/root/.claude/plans/1-dynamic-dawn.md`](../../root/.claude/plans/1-dynamic-dawn.md)
파일에 정리되어 있습니다.

## 모노레포 구조

```
apps/
  api/          FastAPI 백엔드 (라우터, 모델, 서비스)
  web/          Next.js 14 프런트엔드
  worker/       Celery 워커 + Beat 태스크
packages/
  generators/   채널별 콘텐츠 생성기 (순수 함수)
  integrations/ Threads, Maily, Honcho, PDF 어댑터
  shared/       Enum, frontmatter, 브랜드 규칙
infra/          Docker, alembic, 환경설정
legacy/         기존 CLI 스크립트 (참조용)
tests/          pytest 단위 테스트
```

## 빠른 시작 (Docker)

```bash
cp .env.example .env       # ANTHROPIC_API_KEY 등 설정
make up                    # postgres·redis·api·worker·beat·web 기동
make migrate               # 스키마 생성
make seed                  # 관리자 계정 + 기본 브랜드 프로필
open http://localhost:3000 # 로그인 후 사용
```

기본 관리자: `.env`의 `ADMIN_EMAIL` / `ADMIN_PASSWORD` (예: `admin@dreamgrow.local` / `changeme`)

## 핵심 사용 흐름

1. `/contents/new` — 채널 + 주제 입력 → AI 초안 자동 생성 (Celery 잡, SSE 진행 표시)
2. `/contents/[id]` — CodeMirror 마크다운 에디터로 편집, 미리보기/AI원본 Diff/검수 탭
3. 우측 패널 → "검수 실행" — `packages/shared/rules.py`의 규칙으로 이슈 표시
4. "예약" — 캘린더에 등록 → Beat의 60초 sweep이 자동 발행 잡 enqueue
5. `/analytics` — `poll_threads_analytics` (30분 주기)가 수집한 스냅샷 시각화
6. `/learning` — 야간 `run_diff_learning`이 AI 초안 ↔ 사용자 편집을 비교해 패턴 학습

## 개발

```bash
# API 단독 실행 (Docker 없이)
pip install -r apps/api/requirements.txt -r apps/worker/requirements.txt
alembic -c infra/alembic.ini upgrade head
uvicorn apps.api.main:app --reload

# Worker
celery -A apps.worker.celery_app worker --loglevel=info
celery -A apps.worker.celery_app beat   --loglevel=info

# Web
cd apps/web && npm install && npm run dev
```

## 테스트

```bash
pytest -q       # 규칙·frontmatter·generators·threads splitter
```

## 향후 확장 포인트

- 멀티 사용자 / 워크스페이스: 도메인 테이블에 `workspace_id` 컬럼 추가 + Postgres RLS
- 결제·플랜 관리, NextAuth 외부 OAuth 도입
- Apple Notes / Obsidian 원클릭 동기화 UI
- 영상 자동 업로드 (현재는 스크립트 생성까지만)
- Sentry / OpenTelemetry 트레이싱
