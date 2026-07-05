# 플라우드(Plaud) MCP 연동 — 제텔카스텐·콘텐츠 자동화 확장

> 작성: 2026-07-05 · 브랜치 `claude/plaud-mcp-setup-6j07l1`
> 실행 스킬: `.claude/skills/plaud-zettel` (`/plaud-zettel`)

## 무엇을 하려는가

플라우드 녹음기(음성 메모·회의·강의)를 드림그로우 지식 생산 라인의 **최상류 입력**으로 붙인다.

```
플라우드 녹음 (생각·회의·강의·독서 메모)
   │  MCP: list_files / get_note / get_transcript
   ▼
제텔카스텐 (노션 DB) ── 임시/문헌/영구 노트, 노트 간 연결
   │  콘텐츠 씨앗 판정 (학부모 고민 적합성)
   ▼
드림그로우 파이프라인 intake 카드 (stage=intake, status=queued)
   │  기존 오케스트레이터 (30분 cron)
   ▼
리서치 → 키워드 → 브리프 → 토론 초안 → 검수 → ⏸️발행 승인 → Threads/스티비
```

기존 파이프라인은 `daily_intake.py`(AI 발제)와 사람의 수동 카드 생성만 입력원이었다.
플라우드가 붙으면 **사용자의 실제 생각·경험이 씨앗**이 되므로, 브랜드 보이스(경험 기반
공감형)와 가장 잘 맞는 소재가 상류에서 공급된다.

## 설치 상태 (완료)

| 항목 | 내용 |
|---|---|
| MCP 서버 | `.mcp.json`(프로젝트 스코프) — `npx -y @plaud-ai/mcp@latest` (stdio) |
| 스킬 | `.claude/skills/plaud-{shared,browse,find,read,digest,followup,export}` (공식 7종) + `plaud-zettel` (자체 제작 프로세스 스킬) |
| 인증 토큰 | `~/.plaud/tokens-mcp.json` (OAuth, 자동 갱신) — **컨테이너 세션에는 저장 안 됨** |

공식 스킬은 `npx @plaud-ai/mcp install`이 `~/.claude/skills/`에 설치하는 것을 저장소로
복사한 것. 원격 세션은 컨테이너가 매번 초기화되므로 저장소 동봉이 유일한 영구화 방법이다.

## 인증 — 환경별 방법

플라우드 MCP는 OAuth(브라우저 콜백) 방식이다. 환경에 따라:

| 환경 | 방법 |
|---|---|
| **로컬 Claude Code / Desktop** | 첫 플라우드 도구 호출(또는 `login` 도구) 시 브라우저가 열림 → 로그인 1회 → `~/.plaud/tokens-mcp.json`에 저장, 이후 자동 갱신 |
| **claude.ai / Claude Code 웹** | 콜백이 컨테이너 localhost로 향해 stdio 방식은 실패. 대신 **claude.ai 설정 → 커넥터 → 커스텀 커넥터 추가**에 원격 엔드포인트 `https://mcp.plaud.ai/mcp` 등록 → 브라우저에서 정상 OAuth. 등록하면 모든 웹 세션에서 노션처럼 사용 가능 |
| **GitHub Actions (cron)** | 현재 불가 — 비대화형 인증 수단 없음. 아래 "다음 단계" 참고 |

## 제텔카스텐 설계 (노션)

`/plaud-zettel` 첫 실행 시 노션에 "제텔카스텐" DB를 찾거나 생성한다.

- **원자성**: 노트 1개 = 아이디어 1개, 명제형 제목, 자기 말로 3~7문장.
- **유형**: `임시`(즉흥 아이디어) → `문헌`(출처 있는 요약) → `영구`(결합·일반화된 통찰).
  임시 노트 여러 개가 결합되면 영구 노트로 승격 — 지식이 "자라는" 지점.
- **출처 추적**: 모든 노트에 `plaud:<file_id>` 기록. 이 필드가 중복 처리 방지 로그를 겸한다.
- **콘텐츠 승격**: 학부모 고민 적합 + 브랜드 보이스 적합 + 파이프라인 중복 없음 →
  intake 카드 자동 생성(본문에 근거 노트 링크). 애매하면 "승격 후보"로 사람 판단에 넘긴다.

## 운영 방법

- **수동 트리거(현재)**: 아무 세션에서 "플라우드 정리해줘" 또는 `/plaud-zettel` →
  최근 7일 녹음 처리 → 노트 생성·연결·승격 → 결과 표 보고.
- **권장 리듬**: 주 1~2회. `plaud-digest`(주간 다이제스트)와 묶어 "주간 지식 정리" 루틴으로.

## 다음 단계 (미구현 — 우선순위 순)

1. **claude.ai 커넥터 등록** *(사용자 액션, 5분)*: 위 표의 웹 인증 방법. 이것만 하면
   원격 세션에서도 `/plaud-zettel`이 바로 돈다.
2. **제텔카스텐 DB ID를 CLAUDE.md에 고정**: 첫 실행에서 DB가 만들어지면 "핵심 ID" 섹션에 추가.
3. **cron 자동화 (선택)**: `platform.plaud.ai/developer/api`에서 개발자 API 키
   (`PLAUD_CLIENT_ID`/`PLAUD_CLIENT_SECRET`)를 발급받을 수 있으면 `orchestrator/plaud_ingest.py`를
   추가해 daily-intake처럼 매일 자동 수집 가능. 발급 가능 여부 확인이 선행 과제.
4. **문체 학습 연결 (선택)**: 플라우드 전사(사용자의 실제 말투)를 `style_learn.py`의
   학습 소스로 추가하면 작가 에이전트 문체가 사용자 육성에 더 가까워진다.
