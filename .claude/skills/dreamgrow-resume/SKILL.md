---
name: dreamgrow-resume
description: 드림그로우 콘텐츠 자동화 작업을 새 세션에서 이어간다. 컨텍스트가 길어져 새 채팅을 시작했을 때, 현재 시스템 상태(볼트 카드, PR, 미완료 작업)를 빠르게 파악하고 작업을 재개한다. "이어서 작업", "드림그로우 이어가기", "핸드오프", "지금 상태 어디까지" 같은 요청에 사용.
---

# 드림그로우 작업 이어가기

컨텍스트가 길어져 새 세션을 시작했을 때, 이전 작업을 끊김 없이 이어가기 위한 스킬이다.

## 1단계: 맥락 로드 (필수)

1. `CLAUDE.md`를 읽는다 — 프로젝트 구조, 핵심 ID, 운영법, **현재 상태/미완료 작업**이 모두 여기 있다.
2. 필요하면 `docs/ARCHITECTURE_V2.md`로 설계 세부를 확인한다.

## 2단계: 실제 상태 점검

CLAUDE.md의 "현재 상태"는 갱신이 늦을 수 있으니, 실제를 확인한다:

1. **볼트 파이프라인 카드** 조회 — 처리 대기/승인 대기 카드를 본다.
   - 카드 폴더: `vault/파이프라인/활성/`(처리 중) · `vault/파이프라인/발행완료/`(완료). 볼트 루트는 `DG_VAULT_ROOT`(기본 `vault/`).
   - `Glob`/`Grep`으로 카드 md를 훑고, 특정 카드는 `Read`로 연다. frontmatter의 stage/status/approval_status를 본다.
   - 주목: `stage`가 `keyword_approval`/`approval`이고 `status=needs_human`인 카드 = 사용자 승인 대기.
2. **GitHub** 확인 — 열린 PR과 main 머지 상태, 최근 Actions 실행 결과.
   - 열린 PR: `mcp__github__list_pull_requests` (owner=dream0grow, repo=dream-grow-content-automation)
   - 최근 orchestrator 실행: `mcp__github__actions_list` (list_workflow_runs, resource_id=orchestrator.yml)
3. **브랜치 확인** — 모든 개발은 `claude/fervent-bell-0iwlia`에서. 로컬 origin/main 참조는 오래됐을 수 있으니 GitHub를 신뢰.

## 3단계: 사용자에게 요약 + 다음 할 일 제시

다음을 한눈에 보고한다:
- 승인 대기 중인 볼트 카드 (키워드 승인 / 발행 승인)
- 머지 안 된 PR (있으면 머지 안내)
- CLAUDE.md의 "미완료 작업" 항목
- 즉시 할 수 있는 다음 액션 1~3개

## 작업 규칙 (이 프로젝트 공통)

- 코드 변경은 `claude/fervent-bell-0iwlia` 브랜치에 커밋 → PR 생성. 커밋 메시지 끝에 세션 링크.
- Claude는 GitHub Actions를 **직접 실행 못 함**(403). orchestrator/test 실행은 사용자가 Run workflow 클릭.
- 큰 작업(여러 파일 읽기, CSV/볼트 카드 대량 분석)은 서브에이전트(Agent)로 위임해 컨텍스트 절약.
- 작업을 마치거나 컨텍스트가 길어지면 **CLAUDE.md의 "현재 상태" 섹션을 갱신**해 다음 세션이 이어받게 한다.

## 컨텍스트 길어질 때 핸드오프

이 대화가 길어지면:
1. CLAUDE.md "현재 상태"를 최신으로 갱신하고 커밋·푸시한다.
2. 사용자에게 "새 채팅을 시작하고 `/dreamgrow-resume`를 호출하면 이어집니다"라고 안내한다.
3. 새 세션은 CLAUDE.md를 자동으로 읽으므로 맥락이 유지된다.
