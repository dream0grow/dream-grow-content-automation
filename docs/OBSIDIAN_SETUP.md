# 옵시디언 볼트(초생산) ↔ GitHub 연동 가이드

> 결정 사항 (2026-07-06): 볼트를 GitHub 저장소로 동기화한다.
> 이 저장소의 `vault/` 폴더가 볼트이며, 자동화(GitHub Actions)가 여기에 노트를 쓴다.
> 로컬에서는 Obsidian Git 플러그인으로 같은 폴더를 열어 동기화한다.

## 구조

```
[GitHub Actions]  플라우드 녹음 → LLM 가공 → vault/에 노트 커밋·푸시
       ↕  (git)
[내 컴퓨터]  이 저장소 clone → vault/를 옵시디언 볼트로 열기 → Obsidian Git이 pull/push
```

코드(orchestrator/, vault_pipeline/)와 볼트(vault/)는 같은 저장소에 있지만,
볼트 안에는 md와 첨부만 둔다(볼트 헌법 `vault/CLAUDE.md`).

## 1회 설정 (약 15분)

### ① 저장소 clone

```bash
git clone https://github.com/dream0grow/dream-grow-content-automation.git
```

### ② 옵시디언에서 볼트 열기

옵시디언 → "Open folder as vault" → clone한 폴더 안의 `vault/` 선택.
(기존 로컬 「초생산」 볼트는 그대로 두고, 이관은 아래 ⑤에서.)

### ③ Obsidian Git 플러그인 설치

설정 → 커뮤니티 플러그인 → "Git" (Vinzent 제작) 설치·활성화.
볼트가 저장소의 하위 폴더이므로 플러그인 설정에서:

- **Custom base path (git repository path)**: `..` 입력
  (git 저장소 루트가 볼트의 한 단계 위라는 뜻)
- Pull/Push 자동화: "Auto pull interval" 10분, "Auto commit-and-push interval" 30분 권장
- Commit message: `볼트: {{date}}` 등 원하는 형식

### ④ GitHub Secrets 등록 (자동화용)

저장소 → Settings → Secrets and variables → Actions:

| Secret | 값 | 비고 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (기존 등록됨) | LLM 가공 |
| `PLAUD_TOKENS_JSON` | 로컬 `~/.plaud/tokens-mcp.json` 파일 내용 전체 | 선택 — 아래 참고 |

**PLAUD_TOKENS_JSON 만드는 법**: 로컬 Claude Code(또는 Claude Desktop)에서 플라우드
MCP에 1회 로그인(`npx -y @plaud-ai/mcp@latest` 첫 호출 시 브라우저 로그인)하면
`~/.plaud/tokens-mcp.json`이 생긴다. 이 파일 내용을 그대로 Secret에 붙여넣는다.

**토큰 수명과 자동 갱신**: 플라우드 access 토큰은 하루, refresh 토큰은 약 1주로 짧다.
워크플로우가 실행 중 갱신된 토큰을 **Actions 캐시로 다음 실행에 이어받으므로**,
파이프라인이 주기적으로(최소 주 1회) 도는 한 Secret을 다시 등록할 필요가 없다.
파이프라인이 1주 이상 멈춰 refresh 토큰까지 만료되면 로그에 "토큰 만료" 경고가 남는다
→ 로컬에서 재로그인 후 Secret 갱신(캐시는 자동으로 새 토큰으로 대체된다).
GitHub Actions 캐시는 7일 미사용 시 삭제되므로 매일 도는 기본 스케줄이면 충분하다.

**Secret이 없어도 동작한다**: `vault/수집함/plaud/`에 전사 md 파일을 넣으면
(클로드 세션에서 "플라우드 전사 내보내줘" 또는 수동 붙여넣기) 다음 실행 때 처리된다.

### ⑤ 기존 초생산 볼트 이관 (dry-run 필수)

기존 볼트 4,200여 파일을 v2.1 새 구조로 복사한다. **원본은 건드리지 않는다.**

```bash
cd dream-grow-content-automation
# 1. 계획 확인 (아무것도 복사 안 함)
python3 tools/vault_migrate.py "/path/to/기존/초생산" vault/
# 2. 계획이 맞으면 실행
python3 tools/vault_migrate.py "/path/to/기존/초생산" vault/ --execute
# 3. 비밀값 스캔 — 반드시 통과 후 커밋
python3 tools/vault_secret_scan.py vault/
# 4. 커밋·푸시
git add vault/ && git commit -m "볼트: 기존 초생산 이관" && git push
```

이관 매핑(통합기획 v2.1 PART 4):

| 원위치 | 새 위치 |
|---|---|
| 제텔카스텐/5. 제텔카스텐/1~4단계 | 제텔카스텐/1. 메모 ~ 4. 주장 |
| 5단계 - 두번째 뇌 | 제텔카스텐/5. 글감 |
| _검토필요 (613개) | 제텔카스텐/_검토대기 |
| 0. 지식창고 | 제텔카스텐/0. 시스템 |
| raw/, wiki/, SNS 콘텐츠 제작 시스템/ | 그대로 |
| 책 프로젝트 / 스토리 메이커 / 투자 | 프로젝트/책_초등부모 · 꿈들 · 투자 |
| 예시(제레미)·_정리작업·_복원중복 | _archive/ |
| **제텔카스텐/1. 개인/** | **이관 안 함** — 개인정보는 볼트 밖으로 |

### ⑥ 🚨 비밀값 정리 (이관 전 필수)

2026-07-06 스캔에서 기존 볼트 안에 다음이 발견됐다. **이관·커밋 전에 원본에서 지우고, 키는 전부 재발급하라**:

- `raw/Roam-Export-…/March 13th, 2025.md` — **Anthropic API 키 + OpenAI 키**
- `raw/Roam-Export-…/February 10th, 2025.md` — OpenAI 키 2건
- `raw/Roam-Export-…/February 19th, 2026.md` — GitHub 토큰
- `raw/Roam-Export-…/May 31st, 2023.md` 외 3곳 — 주민등록번호 패턴

`tools/vault_secret_scan.py`가 같은 검사를 하며, Actions 워크플로우도 커밋 전에 이 검사를 강제한다.

## 매일 운영

1. **자동**: 매일 밤 KST 22:08 `plaud-pipeline` 워크플로우가 최근 녹음을 가공해 커밋.
2. **아침 (5분)**: 옵시디언에서 pull → `_system/review_queue.md` 결재(노랑 사례 승인/반려)
   → `발행/블로그_교사/`·`발행/페이스북_교사/` 초안 확인, 마음에 들면 복사해 발행하고
   frontmatter `상태: 발행완료`로 변경.
3. **수동 실행**: GitHub Actions 탭 → plaud-pipeline → Run workflow
   (Claude는 권한상 직접 실행 불가, 사용자가 클릭).
