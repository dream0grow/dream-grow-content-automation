# 아키텍처 메모

## 동기/비동기 경계

| 동작 | 어디서 처리하나 | 이유 |
|---|---|---|
| 인증/CRUD/검수 규칙 | FastAPI(동기 HTTP) | 빠르게 응답 가능 |
| LLM 생성, Threads/Maily 발행 | Celery 워커 | 5~60초 소요, 외부 API 다단계 호출 |
| 스케줄 sweep, 분석 폴링, 야간 학습 | Celery Beat | 주기 작업 |

워커는 `jobs` 행을 갱신하고 Redis `job:<id>` 채널에 진행 이벤트를 발행합니다.
API의 `GET /api/v1/events/stream?job_id=...`가 SSE로 그대로 중계합니다.

## DB 설계 원칙

- ULID(`CHAR(26)`) PK: 시간순 정렬 가능, 단일 호스트에서 안전
- `contents`는 `ai_original_md` 컬럼으로 초기 생성 본문을 보존해 diff 학습 원본 확보
- `frontmatter JSONB`로 기존 Obsidian 키 무손실 보존 (`주제/채널/상태/...`)
- `(workspace_id, ...)` 인덱스는 단일 사용자에서는 단순 컬럼 인덱스로 시작

## 비밀 관리

- `JWT_SECRET`: 액세스/리프레시 JWT 서명
- `KEY_VAULT_KEY`: 외부 자격증명 Fernet 암호화 키
- `integration_credentials.encrypted_payload`: 외부 API 토큰 (`access_token`, `user_id` 등)
- API 응답에는 자격증명 원본을 절대 노출하지 않고 `status`와 `connected`만 반환

## 멀티테넌트 확장 시

1. 모든 도메인 테이블에 `workspace_id CHAR(26) NOT NULL` 추가
2. 인덱스 prefix를 `(workspace_id, ...)` 형태로 재작성
3. Postgres RLS 정책: `USING (workspace_id = current_setting('app.workspace_id')::text)`
4. FastAPI `get_workspace` 의존성을 추가하고 `SET LOCAL app.workspace_id` 호출
5. NextAuth 도입 + 워크스페이스 스위처 UI

## 기존 코드 매핑

| 기존 | 새 위치 | 주된 변경 |
|---|---|---|
| `legacy/claude_client.py` | `apps/api/services/llm.py` | CLI 경로 하드코딩 제거, Anthropic SDK 우선 |
| `legacy/thread_generator.py` | `packages/generators/thread.py` | I/O 제거, 순수 함수화 |
| `legacy/threads_publisher.py` | `packages/integrations/threads/publisher.py` | 파일 입력 대신 본문 문자열, 결과 객체 반환 |
| `legacy/threads_insights.py` | `packages/integrations/threads/insights.py` | fetch/parse만 분리 |
| `legacy/maily_integration.py` | `packages/integrations/maily/client.py` | 클래스 기반, env 의존 제거 |
| `legacy/memory_manager.py` | `packages/integrations/honcho/memory.py` | 인자로 키 주입 |
| `legacy/content_reviewer.py` | `packages/shared/rules.py` + `apps/api/services/validator.py` | 규칙 데이터와 실행 분리 |
| `legacy/diff_learner.py` | `apps/worker/tasks/learning.py` | `ai_original_md` 컬럼 사용 |
| `legacy/lead_magnet_pdf.py` | `packages/integrations/pdf/render.py` | 폰트 경로 env 주입, bytes 반환 |
| `legacy/scheduled/*.plist` | `apps/worker/celery_app.py` beat 스케줄 | macOS 의존 제거 |
