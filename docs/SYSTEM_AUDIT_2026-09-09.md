# 드림그로우 SNS 콘텐츠 자동화 — 전체 코드 점검 보고서 (2026-09-09)

> 조사 범위: 저장소 전체(루트 스크립트 23개, `orchestrator/` 36개, `vault_pipeline/` 18개, `tools/` 7개, `agents/`·`scheduled/`·`youtube/`·`skills-draft/`·`dashboard/`, 워크플로우 15개, 볼트 카드 79장, GitHub Actions 실행 이력).
> 검증 방법: 코드 정독 + 호출 관계 grep + GitHub Actions 실행 로그 + 볼트 frontmatter 집계 + 테스트 173종 실행(전부 통과).

---

## 0. 한 줄 결론

**겉으로는 모든 워크플로우가 "success"지만, 새 글이 만들어지는 입구(리서치)는 2026-08-24부터 완전히 멈춰 있습니다.** 그 뒤에 만들어진 카드 17장이 전부 `research/queued`라는 아무도 집어가지 않는 상태로 갇혀 있고, 텔레그램 통지도 나가지 않았습니다. 원인은 두 가지가 겹쳤습니다.

1. **Manus API 키가 401(인증 실패)로 죽었습니다.** 그런데 코드는 "키가 있으면 Manus"라고만 판단해 Claude 폴백을 타지 않습니다.
2. **실패 재시도 로직의 상태 불일치 버그**입니다. `handle_intake`가 먼저 `stage=research`로 바꿔 놓은 뒤 예외가 나면, 재시도 로직은 `status=queued`로만 되돌립니다. 그 결과 `research/queued`가 되는데, 이 조합을 처리하는 DISPATCH 항목이 없습니다. 1회 자동 재시도도, 실패 통지도 일어나지 않고 영원히 멈춥니다.

그 앞단(발제)과 뒷단(발행, 릴스 추천, 플라우드, 소크라테스, 썸네일 시트)은 정상 가동 중입니다. 다만 **발행 승인 대기 카드 44장, 리뷰 대기 원고 448건, 프롬프트 개선 큐시트 9장이 사람 손을 기다리며 쌓여 있어** "자동화가 사람 병목에 막혀 있는" 구조가 뚜렷합니다. 3개월(6월 13일 이후) 동안 실제 Threads 발행은 4건입니다.

---

## 1. 지금 실제로 돌아가는 흐름

### 1-1. 워크플로우 15개 — 실행 상태

| 워크플로우 | 주기 | 실행 모듈 | 최근 상태 | 실제 판정 |
|---|---|---|---|---|
| `orchestrator.yml` | 15분 (`8,23,38,53`) | `orchestrator.run` → `telegram_assistant` → `script_feedback` | 1,491회, 전부 success | ⚠️ **겉만 성공**. Run 단계가 2초 만에 끝남 — intake 1건 집고 Manus 401로 실패 → "0개 카드 처리". 뒤 두 단계는 정상(미처리 메시지 0, 피드백 0). |
| `daily-intake.yml` | 매일 07:10 KST | `orchestrator.daily_intake` | 70회 success, 09-09 카드 생성 | ✅ 정상. 그러나 만든 카드가 전부 위 버그로 사망 → **하루 1장씩 시체를 만드는 중** |
| `thumbnail.yml` | 2시간 | `orchestrator.thumbnail --sheet` | 157회 success | ⚠️ **무한 재렌더 루프**. 08-20부터 시트 12행(초등 고전 독서) 같은 행을 매회 다시 렌더 → 이미지 322장(78MB) 볼트에 누적 커밋. OpenAI 429, Pexels 403이라 실제로는 그라데이션 배경. 텔레그램 시크릿이 이 워크플로우에 없어 알림 0장. |
| `youtube-body.yml` | 2시간 | `orchestrator.youtube_body` | 141회 success | ✅ 정상(대기 행 없어 20초 종료). 장부에 4행 처리 기록. |
| `plaud-pipeline.yml` | 매일 22:08 KST | `vault_pipeline.run` → `feedback` | 69회 success | ✅ 정상 가동(09-09 로그 존재) |
| `vault-agents.yml` | 매일 05:08 KST | `vault_pipeline.socrates` | 65회 success | ✅ 정상(09-08 새벽 질문 커밋) |
| `reels-recommend.yml` | 월~금 06:20 KST | `vault_pipeline.reels_recommend` | 10회 success | ✅ 정상. 누적 36편 추천, 최근 09-09 08:27 |
| `self-improve.yml` | 주 1회 + 매일 apply | `orchestrator.self_improve` | 103회 success | ⚠️ 큐시트 9장 제출됐지만 **한 번도 승인된 적 없음** → 프롬프트 개선이 실제로 반영된 적 없음 |
| `cardnews-benchmark.yml` | 주 1회 | `orchestrator.cardnews_benchmark` | 11회 success | ⚠️ 매주 `data/cardnews_benchmark.md` 갱신·커밋하지만 **읽는 곳이 수동 test-cardnews뿐** — 실효 없음 |
| `weekly-snapshot.yml` | 일요일 | git tag만 | 9회 success | ✅ 정상(스냅샷 태그) |
| `telegram-oneshot.yml` | push 트리거 | 인라인 파이썬 | 3회 success | ✅ 세션에서 텔레그램 보내는 통로, 정상 |
| `backfill-2cha.yml` | 수동 | `run --stage rubric_backfill` | 실행 이력 0 | 기타(일회성) |
| `test-cardnews.yml` | 수동 | `orchestrator.cardnews` | 07-02 이후 미실행 | 기타(수동 검증용) |
| `test-reels-video.yml` | 수동 | `orchestrator.reels_video` | 1회 **실패** (Muapi 404) | ❌ 릴스 영상 생성은 한 번도 성공한 적 없음 |
| `test-stibee.yml` | 수동 | `orchestrator.test_stibee` | 07-02 이후 미실행 | 기타(수동 검증용) |

GitHub에는 `notify-top-reels.yml`, `orchestrator-kick.yml` 두 개가 더 보이지만, main에는 없고 옛 `claude/*` 브랜치에만 남아 있는 잔재입니다(원격 브랜치 50개 잔존).

### 1-2. 볼트 카드 79장 — 어디에 멈춰 있나

| 상태 | 장수 | 의미 |
|---|---|---|
| `approval / needs_human / requested` | **44** | 초안 완성, **사람의 발행 승인 대기** (07-08 ~ 09-03 생성) |
| `research / queued` | **17** | Manus 401 + 재시도 버그로 **영구 고아** (08-24 DG-0059부터 매일 1장) |
| `analysis / needs_human` | 9 | 프롬프트 개선 큐시트, 미승인 누적 (07-13부터 매주 1장) |
| `draft / needs_human / youtube` | 5 | 유튜브 롱폼 원고 완성(종착지=촬영, 정상) |
| `published / done` | 4 | DG-0008, 0023, 0033, 0065 — Threads 발행 완료 |

`05 리뷰/대기`에는 448건(스레드 열람 사본 264, 릴스 원고 122, 뉴스레터 18, 유튜브 14, 썸네일 6 등)이 있고 거의 전부 `리뷰대기`입니다. `05 리뷰/완료`는 4건입니다.

### 1-3. 설계 흐름 vs 실제 흐름

```
[설계]  intake → research(Manus) → keyword → (자동승인) → brief → draft(토론) → approval ⏸️ → publish
[실제]  intake → research/queued ✖ (여기서 사망, 08-24 이후 전건)
                 └ 그 이전 카드 44장은 approval ⏸️ 에서 사람 대기
```

Manus는 401 이전부터도 불안정했습니다. 활성 카드 44장에 `⚠️ Manus 리서치 우회` 섹션(25분 초과 → Claude 폴백)이 남아 있습니다. 즉 지금까지 만들어진 초안의 리서치는 **대부분 Claude 폴백**이 한 것입니다. Manus는 비용만 들고 실효가 거의 없었습니다.

---

## 2. 코드 연동 지도 (누가 누구를 부르는가)

### 2-1. 자동 파이프라인 핵심 (cron이 직접 실행)

```
orchestrator.yml
 └ orchestrator/run.py            stage 상태 머신 (DISPATCH 8항목)
     ├ manus_research.py           Manus 3종 병렬 / Claude 폴백
     ├ naver_keywords.py           네이버 검색광고 실측 검색량
     ├ prompts.py                  브랜드 보이스·룰북·에이전트 프롬프트 26종(전부 사용 중)
     ├ agent_dialogue.py           작가↔비평가↔윤리검수 토론 (data/benchmark_posts.md, hook_patterns.md 주입)
     ├ rubric_review.py            평가표 채점 + 2차안
     ├ review_copy.py              05 리뷰/대기 열람 사본
     ├ youtube_script.py           format: youtube 카드 → 롱폼 원고
     ├ publish.py → stibee.py      Threads 체인 / 스티비 뉴스레터
     ├ style_learn.py → (루트) memory_manager.py → Honcho
     └ state.py → obsidian_state.py → vault_pipeline/telegram_notify.py
 └ vault_pipeline/telegram_assistant.py   일반 메시지 의도 판별 → reels_recommend / script_feedback
 └ vault_pipeline/script_feedback.py      원고 알림 + 답장 피드백 반영
 └ tools/vault_secret_scan.py             커밋 전 비밀값 게이트

daily-intake.yml  → orchestrator/daily_intake.py → state.create_card
thumbnail.yml     → orchestrator/thumbnail.py → gsheet.py, image_gen.py, cardnews.py(폰트·사진 함수), llm.call_vision
youtube-body.yml  → orchestrator/youtube_body.py → gsheet.py, youtube_script.py, thumbnail.col_letter
plaud-pipeline.yml→ vault_pipeline/run.py → plaud_client, writers, vault_io, prompts / feedback.py
vault-agents.yml  → vault_pipeline/socrates.py
reels-recommend.yml → vault_pipeline/reels_recommend.py
self-improve.yml  → orchestrator/self_improve.py → (루트) memory_manager, diff_learner
```

공통 기반: `orchestrator/llm.py`(저장소 최다 참조, 키 없으면 루트 `claude_client.py` CLI 폴백), `orchestrator/config.py`, `vault_pipeline/vault_io.py`(orchestrator 4개 모듈도 역참조).

### 2-2. 수동 실행 계층 (사람이 Run workflow 또는 CLI)

`cardnews.py`(+`card_editor.py`, `photo_judge.py`, `stock.py`) → test-cardnews.yml / `reels_video.py` → test-reels-video.yml / `preview.py` → 실행 워크플로우 없음, `cardnews`가 `pick_topic` 한 함수만 빌려 씀 / `tools/shorts_edit.py` → 스킬 `dreamgrow-shorts-editor` / `tools/naver_blog_scrape.py` → 맥북 전용 / `dashboard/index.html` → 브라우저에서 직접 열기.

### 2-3. 아무도 부르지 않는 계층 (레거시 v1)

루트 23개 스크립트 중 20개, `agents/team_runner.py`, `scheduled/` launchd 6종, `skills-draft/`, `youtube/`(타 프로젝트 소유). 자세한 목록은 4절.

---

## 3. 발견한 버그·정지 원인 (근거 포함)

| # | 심각도 | 증상 | 원인 (파일:위치) | 영향 |
|---|---|---|---|---|
| B1 | 🔴 | 08-24 이후 신규 카드 전부 `research/queued`에서 정지, 통지 없음 | `run.py` `_REQUEUE_STATUS["intake"]="queued"`인데 `handle_intake`가 먼저 `stage=research`로 갱신함 → `research/queued`는 DISPATCH 8항목 어디에도 없음. `_sweep_stale_running`도 brief/draft만 훑음 | 카드 17장 고아. 매일 1장씩 증가 |
| B2 | 🔴 | Manus `task.create` 401 Unauthorized | `manus_research.available()`이 키 **존재 여부만** 확인. `_request_with_retry`는 429/5xx만 재시도, 401은 즉시 raise | Claude 폴백을 못 탐 → B1 트리거 |
| B3 | 🟠 | 썸네일 시트 12행이 2시간마다 재렌더 (08-20~, 157회) | `gsheet.read`가 기본 `FORMATTED_VALUE`로 읽어 R열 `=IMAGE()` 수식 셀이 빈 문자열로 옴 → `find_render_ready`가 매번 "R 비어 있음"으로 판정 | 이미지 322장(78MB) 볼트 커밋, 이미지 API 호출 낭비(OpenAI 429의 원인일 가능성) |
| B4 | 🟠 | 썸네일 렌더 텔레그램 "0장" | `thumbnail.yml` env에 `TELEGRAM_BOT_TOKEN`/`CHAT_ID` 없음 | 썸네일 완성 알림이 한 번도 안 감 |
| B5 | 🟠 | AI 배경 생성 실패 | OpenAI 이미지 API 429(쿼터/과금), Pexels 403(키 무효), Unsplash 키 미설정 | 썸네일·카드뉴스 배경이 그라데이션 폴백 |
| B6 | 🟠 | 릴스 영상 생성 404 | Muapi `POST /api/v1/seedance-lite-t2v` Not Found — 모델 경로 또는 키 문제 | `reels_video.py`는 실전 성공 이력 0 |
| B7 | 🟡 | 프롬프트 개선 큐시트 9장 미승인 | `analysis` stage는 DISPATCH에 없고 사람이 `approval_status: approved`로 바꿔야만 `--apply`가 동작 | 자가 학습 루프가 한 번도 닫힌 적 없음 |
| B8 | 🟡 | 발행완료 카드가 활성 폴더에 남음 | `obsidian_state._done_dir()`로 옮기는 코드가 없음 | 활성 폴더 무한 증가, `query_cards(page_size=20)` 파일명 정렬 조기 break로 뒤쪽 카드 누락 위험 |
| B9 | 🟡 | 비밀값 스캔 게이트 누락 | `thumbnail.yml`, `youtube-body.yml`의 볼트 커밋 단계에 `vault_secret_scan.py`가 없음 (다른 6개 워크플로우엔 있음) | 07월 키 유출 사고 재발 통로 |
| B10 | 🟡 | 발행 토큰 미설정 시 무알림 정지 | `publish.py` `available()` False 경로가 `notify()`를 안 부름 | 조용히 needs_human |
| B11 | ⚪ | `daily_intake`가 `format=`을 안 넘김 | `create_card(format=...)` 미지정 → 모든 발제 카드가 스레드 고정 | 뉴스레터·유튜브 발제 불가 |
| B12 | ⚪ | git 이력이 09-06 루트 커밋 하나로 재시작(50커밋) | 이전 이력 소실(HISTORY.md로만 추적 가능). 원격 `claude/*` 브랜치 50개 잔존 | 감사 추적 약화 |

---

## 4. 코드 5분류

### 4-1. ✅ 계속 유지 코드 (자동 배선 + 정상 동작 + 테스트 있음)

| 파일 | 역할 | 비고 |
|---|---|---|
| `orchestrator/state.py`, `obsidian_state.py` | 카드 저장소 파사드/구현 | B8(아카이브 이동 없음)은 업데이트 항목으로 별도 기재 |
| `orchestrator/llm.py` | Anthropic 래퍼 + Claude CLI 폴백 | 최다 참조. 재시도/백오프 없음(개선 여지) |
| `orchestrator/prompts.py` | 프롬프트 26종 | **미참조 상수 0개** |
| `orchestrator/agent_dialogue.py` | 작가↔비평가↔윤리 토론 | draft 단계 필수 |
| `orchestrator/naver_keywords.py` | 네이버 검색량 실측 | 시크릿 등록됨, 죽은 함수 없음 |
| `orchestrator/publish.py` | Threads 체인 발행 + 부분발행 재개 | 실발행 4건 이력. B10만 보완 |
| `orchestrator/rubric_review.py`, `review_copy.py` | 평가표/열람 사본 | review_copy는 content_id 미포함 파일명 충돌 가능(사소) |
| `orchestrator/youtube_script.py`, `youtube_body.py`, `gsheet.py` | 유튜브 롱폼 원고 / 시트 도입부→본문 | youtube-body 2시간 cron 정상. `gsheet.append()`만 미사용 |
| `orchestrator/daily_intake.py` | 매일 발제 | 정상 동작. B11은 업데이트 항목 |
| `orchestrator/config.py` | 환경변수 단일 소스 | 모델 ID 기본값 실재 확인은 3번 항목 |
| `vault_pipeline/run.py`, `plaud_client.py`, `writers.py`, `vault_io.py`, `prompts.py`, `feedback.py` | 플라우드 → 제텔카스텐 파이프라인 | 69회 정상. `@plaud-ai/mcp@latest` 버전 미고정만 유의 |
| `vault_pipeline/socrates.py` | 새벽 질문 | 65회 정상 |
| `vault_pipeline/reels_recommend.py` | 릴스 원고 추천 + 로테이션 장부 | 36편 누적, 정상 |
| `vault_pipeline/script_feedback.py`, `telegram_assistant.py`, `telegram_notify.py` | 텔레그램 핑퐁·비서·알림 | 정상. `_resolve_target` 등 비공개 심볼 크로스 임포트는 정리 여지 |
| `tools/vault_secret_scan.py` | 커밋 전 비밀값 게이트 | 6개 워크플로우에서 사용. B9(2개 누락)는 업데이트 항목 |
| `tools/shorts_edit.py` + 스킬 `dreamgrow-shorts-editor` | 로컬 쇼츠 자동 편집 | 테스트 21종, 워크플로우 미참조는 의도(원본 비업로드) |
| `dashboard/index.html` | 브라우저 발행 대시보드 | 경로가 현행 볼트 구조와 일치, 운영 문서에서 안내 중 |
| 워크플로우: `orchestrator`, `daily-intake`, `youtube-body`, `plaud-pipeline`, `vault-agents`, `reels-recommend`, `telegram-oneshot`, `weekly-snapshot` | | |
| 테스트 13개 파일 173종 | 전부 통과 | |
| 루트 `claude_client.py`, `memory_manager.py` | Claude CLI 폴백 / Honcho 메모리 | **레거시 폴더에 있지만 신형이 실제로 import** (`llm.py`, `style_learn.py`, `prompts.py`, `self_improve.py`, `agent_dialogue.py`). 삭제 금지, `orchestrator/` 하위로 **이동** 권장 |
| `.claude/skills/`·`.claude/agents/` 윤문 스킬·제텔 에이전트 | 세션 내 도구 | 정상 |
| `data/benchmark_posts.md`, `hook_patterns.md`, `thumbnail_patterns.md`, `youtube_voice.md`, `thumbnail_assets/` | 프롬프트 주입 자료 | 전부 로드됨 |

### 4-2. 🔍 확인 필요 코드 (돌고는 있지만 실효·설정을 사용자가 판단해야 함)

| 파일 / 항목 | 확인할 것 |
|---|---|
| `orchestrator/manus_research.py` + `MANUS_API_KEY` 시크릿 | **Manus를 계속 쓸 것인가?** 401로 죽어 있고, 살아 있을 때도 44장이 25분 초과 우회. 키 갱신 또는 시크릿 삭제(→ Claude 폴백 전용) 중 결정 |
| `orchestrator/self_improve.py` + 큐시트 9장 | 큐시트를 승인·반영할 의사가 있는가? 없으면 주간 회고를 끄거나, 큐시트를 **텔레그램 요약 + 자동 반영(가드 포함)**으로 바꿔야 실효 |
| `orchestrator/style_learn.py` | 실제 학습이 일어난 적이 있는지 확인. 텔레그램 답장 → 재초안 경로가 주력이라 "AI 원본 == 최종본"으로 조기 종료할 가능성 큼. Honcho 저장 실패도 print만 함 |
| `orchestrator/stibee.py` + `STIBEE_*` | 뉴스레터 카드가 0장이라 실전 미가동. 독스트링에 "첫 실행 4xx면 payload 조정"이라 검증 미완 명시. 뉴스레터 채널을 운영할지 결정 |
| `orchestrator/config.py` 모델 ID | `claude-opus-4-8`(글쓰기), `claude-sonnet-5`(유틸)이 하드코딩 기본값이고 워크플로우가 덮어쓰지 않음. 현재 성공 로그로 보아 동작은 하지만 최신 모델 정책과 맞는지 확인 |
| `orchestrator/cardnews_benchmark.py` + `cardnews-benchmark.yml` | 매주 돌지만 소비처가 수동 test-cardnews뿐. **카드뉴스를 자동 파이프라인에 붙일 계획이 없다면 cron 중지** |
| `orchestrator/cardnews.py`(+`card_editor.py`, `photo_judge.py`, `stock.py`, `image_gen.py`) | 07-02 이후 실행 없음. 유지할지(카드뉴스 채널) 결정. `photo_judge`는 `llm.call_vision` 중복 구현. `--video-url` 인자는 파싱만 되고 미사용 |
| `orchestrator/reels_video.py` + `MUAPI_API_KEY` | Muapi 404. 모델 경로/키를 고쳐 쓸 것인지, 다른 영상 생성 경로로 갈 것인지 |
| 이미지 API 키 3종 | OpenAI 429(과금/쿼터), Pexels 403(무효), Unsplash 미설정 → 배경 생성이 전부 폴백. 키 갱신 여부 |
| `orchestrator/preview.py` | 실행 워크플로우 없음. CLAUDE.md에는 문서화돼 있어 문서-배선 불일치. 쓸 일이 없으면 삭제 후보 |
| `vault_pipeline/plaud_client.py` | `npx @plaud-ai/mcp@latest` 버전 미고정 → 업스트림 변경 시 조용히 깨짐. 버전 고정 검토 |
| `tools/naver_blog_scrape.py` | 문체 샘플(`raw/블로그글`)을 채우는 유일한 경로인데 맥북 수동 실행. 마지막 실행 시점 확인 |
| `.github/workflows/test-*.yml` 3종 | 수동 검증용. 유지하되 최근 미실행 |
| 원격 `claude/*` 브랜치 50개 | 머지된 것은 삭제해도 무방. 미머지 작업이 있는지 확인 |
| `scheduled/` launchd plist 6종 | **사용자 맥에 아직 load돼 있는지 확인.** 옛 Dropbox 절대경로를 가리켜 매일 헛돌 수 있음 (`launchctl list | grep dreamgrow`) |

### 4-3. 🔧 업데이트 필요 코드 (버그 또는 설계 불일치, 고쳐야 함)

| 파일 | 고칠 내용 | 관련 버그 |
|---|---|---|
| `orchestrator/run.py` | ① `_handle_failure`가 **카드의 현재 stage** 기준으로 재큐하거나 `research/queued`도 DISPATCH에 추가. ② `research` 실패 시 `stage=intake`로 되돌리기. ③ 고아 17장 즉시 구제(`stage: intake, status: queued, last_error: ''`로 일괄 리셋). ④ 주석 "cron 30분" → 15분 | B1 |
| `orchestrator/manus_research.py` | `create_research_tasks`에서 401/403이면 예외 대신 **즉시 Claude 폴백**으로 넘기기(`available()`에 키 유효성 캐시) | B2 |
| `orchestrator/gsheet.py` / `thumbnail.py` | `read()`에 `valueRenderOption=FORMULA` 옵션을 두고 `find_render_ready`가 R열을 수식 기준으로 판정. 또는 완료 색(파랑)을 "이미 렌더됨" 신호로 사용 | B3 |
| `.github/workflows/thumbnail.yml` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` env 추가 + `vault_secret_scan.py` 게이트 추가 | B4, B9 |
| `.github/workflows/youtube-body.yml` | `vault_secret_scan.py` 게이트 추가 | B9 |
| `vault/파이프라인/썸네일/` | 중복 렌더 322장 정리(마지막 1세트만 남기기), 이후 같은 행 재렌더 금지 | B3 |
| `orchestrator/obsidian_state.py` + `run.py` | `published/done` 카드를 `발행완료/`로 이동하는 단계 추가. `query_cards` page_size 조기 break 재검토 | B8 |
| `orchestrator/publish.py` | 토큰 미설정 경로에서도 `notify()` 호출. DG-0008의 오래된 `last_error` 정리 | B10 |
| `orchestrator/daily_intake.py` | `create_card(format=...)` 전달 — `DG_DAILY_FORMAT` 같은 env로 스레드/뉴스레터/유튜브 비율 지정 | B11 |
| `orchestrator/self_improve.py` | 큐시트를 텔레그램으로 요약 통지(현재는 볼트에만 쌓임). `PROPOSED_RULES_JSON` 한 줄 파싱 가정 완화 | B7 |
| `orchestrator/reels_video.py` | Muapi 모델 엔드포인트 확인(문서 재조회) 또는 대체 | B6 |
| `orchestrator/youtube_body.py` | `thumbnail.col_letter` 하나 때문에 1,024줄 모듈(Playwright 체인) 로드 → `gsheet.py`로 이동 | 성능 |
| `orchestrator/photo_judge.py` | `llm.call_vision`으로 통합(중복 제거) | 정리 |
| `orchestrator/review_copy.py` | 파일명에 content_id 포함(서로 다른 카드 충돌 방지). `youtube_script._file_token` 비공개 심볼 의존 해소 | 정리 |
| `vault_pipeline/script_feedback.py`, `reels_recommend.py`, `telegram_assistant.py` | 비공개 심볼(`_resolve_target`, `_script_dir`) 공개 함수로 승격 | 정리 |
| `requirements.txt` | `edge-tts`, `moviepy` 제거(아무도 import 안 함), `google-auth` 명시(gsheet가 사용, 현재는 워크플로우가 따로 설치), `pytest` 개발 의존 명시 | 정합성 |
| `CLAUDE.md` | 상단 "30분 cron" → 15분. "notify-top-reels 삭제"는 main엔 없으나 GitHub 목록엔 남는 이유(옛 브랜치) 명시 | 문서 |

### 4-4. 🗑️ 삭제 요망 코드 (아무도 부르지 않고 후계 모듈이 있음)

| 파일 | 대체 모듈 | 근거 |
|---|---|---|
| 루트 `pipeline.py`, `main.py` | `orchestrator/run.py` + Actions | v1 CLI 오케스트레이터. 참조 0 |
| 루트 `threads_publisher.py`, `scheduled_publisher.py` | `orchestrator/publish.py` | publish.py 헤더에 "이식 완료" 명시 |
| 루트 `newsletter_generator.py`, `maily_integration.py` | `orchestrator/stibee.py` + `prompts.py` | Maily 철수(스티비 대체) 명시. 참조 0 |
| 루트 `youtube_script.py`, `reels_script.py`, `auto_reels_from_thread.py` | `orchestrator/youtube_script.py`, `reels_video.py`, `vault_pipeline/reels_recommend.py` | 동명 신형과 혼동 위험 |
| 루트 `thread_generator.py`, `content_reviewer.py` | `orchestrator/prompts.py` + `agent_dialogue.py`, `rubric_review.py` | 레거시 내부에서만 참조 |
| 루트 `calendar_scheduler.py`, `calendar_sync.py`, `publish_calendar.py`, `daily_planner.py` | 발행 예약은 `publish_at` frontmatter, 알림은 텔레그램 | Google Calendar 연동 폐기. 참조 0 |
| 루트 `sync_wiki.py` | git(vault/ 인리포) | Dropbox↔Obsidian 복사. 소스 폴더 자체가 없음 |
| 루트 `apple_notes_to_zettel.py` + `apple_notes_raw/`(723개, 3.7MB) | `tools/vault_migrate.py`(완료) | 일회성 이관 완료. macOS 전용 |
| 루트 `lead_magnet_pdf.py` | 없음 | `fpdf` 미설치로 이미 import 실패. 참조 0 |
| 루트 `rename_threads.sh` | 임무 종료 | 옛 맥 절대경로(`07 스레드`)의 파일 일괄 개명 스크립트. 현행 볼트에 해당 폴더 없음 |
| `agents/team_runner.py`, `agents/skill-updater.md` | `orchestrator/run.py`, `vault_pipeline/feedback.py` | 모델 `claude-sonnet-4-6`/`opus-4-6` 하드코딩, 옛 볼트 절대경로. `.claude/agents/`가 아니라 로드도 안 됨 |
| `scheduled/` (plist 6종 + `install-schedules.sh` + `weekly-review-report.sh`) | GitHub Actions cron 8종 | 맥 launchd 전용, 존재하지 않는 폴더(`08 리뷰`, `07 스레드`) 참조 |
| `skills-draft/book-rules.md`, `newsletter-generate-SKILL.md` | `.claude/skills/` 17종 | 참조 0, "Opus 4.6"·옛 경로 전제. 규칙 내용이 필요하면 `data/`로 옮긴 뒤 삭제 |
| `tools/vault_migrate.py`, `tools/rename_cards.py` | 임무 종료 | 이관·개명 완료 확인(옛 이름 카드 0건). rename은 멱등이라 남겨도 무해 |
| `data/cardnews_benchmark.json`, `data/스마트폰규칙_thread_2차안.md`, `data/thread_rubric.md` | 각각 write 전용 / 참조 0 / 평가표는 `prompts.RUBRIC_REVIEW`에 인라인 | thread_rubric.md는 문서로 남길 가치는 있음 |
| `.claude/skills/humanize*` 3종 | `im-not-strange-ai*` 3종과 거의 같은 내용(후자가 Sunny 문장 규칙 추가판) | CLAUDE.md도 후자를 기본으로 지정. 한 쪽만 유지 |
| 원격 `claude/*` 브랜치 중 머지 완료분 | | `notify-top-reels.yml`, `orchestrator-kick.yml` 유령 워크플로우도 함께 사라짐 |
| `vault/파이프라인/썸네일/` 중복 렌더 ~300장 | | 78MB. B3 수정과 함께 정리 |

**보류(삭제 전 판단 필요)**: 루트 `diff_learner.py`(`self_improve.py`가 함수 1개 import → 이식 후 삭제), `threads_insights.py`(HISTORY에 "차기 구현, 성과 상위 → 카드뉴스" 계획으로 남음), `lead_magnet_generator.py`(리드마그넷 기능이 신형에 없음 — 리드마그넷을 계속 만들 것인지), `pdf_output/`(볼트 리드마그넷 카드가 깨진 절대경로로 가리킴).

### 4-5. 📦 기타 코드

| 항목 | 성격 |
|---|---|
| `youtube/` 7개 파일 | **타 프로젝트(10x인생/Science Channel) 소유, `OWNERSHIP.md`가 수정 금지 명시.** 이 저장소 자동화와 무관하고 아무도 import 안 함. 삭제·수정 대상 아님 |
| `tools/setup_open_generative_ai.sh` + `docs/open-generative-ai-setup.md` | 선택 설치 도구(GUI 스튜디오). 파이프라인 필수 아님 |
| `.github/workflows/backfill-2cha.yml` | 일회성 백필. 실행 이력 없음 |
| `orchestrator/preview.py` | 사실상 `pick_topic` 한 함수만 생존(4-2 참고) |
| `docs/` 7종 + `docs/기획/` | 설계·이력 문서. `ARCHITECTURE_V2.md`의 "30분 cron"·`HISTORY.md` 등 일부 갱신 필요 |
| `vault/_system/.context/` STATE·HANDOFF | 07-06 시점에서 갱신 멈춤(현행 상태와 불일치) |
| `.github/notify/telegram_oneshot.txt` | telegram-oneshot 메시지 파일. 매번 덮어써 사용 |

---

## 5. 권장 조치 순서

1. **(오늘) 리서치 데드엔드 해소** — `run.py` 재큐 버그 수정 + `manus_research` 401 즉시 폴백 + 고아 17장 리셋. 이것만 고치면 매일 발제 → 초안이 다시 흐릅니다. Manus를 안 쓸 거면 `MANUS_API_KEY` 시크릿을 지우는 것이 가장 빠릅니다(코드가 Claude 폴백을 탑니다).
2. **(오늘) 썸네일 루프 정지** — `gsheet.read` 수식 판정 수정 + `thumbnail.yml`에 텔레그램·비밀값 스캔 추가 + 중복 이미지 정리. 이미지 API 비용 누수를 막습니다.
3. **(이번 주) 사람 병목 재설계** — 발행 승인 대기 44장, 리뷰 대기 448건, 큐시트 9장은 "승인만 하면 된다"는 설계가 현실에서 작동하지 않는다는 증거입니다. 예: 하루 1장만 텔레그램으로 "오늘 발행할 초안" 제안 → 답장 한 글자로 승인, 7일 무응답 카드는 자동 보류 처리 같은 흐름이 필요합니다.
4. **(이번 주) 레거시 정리** — 4-4 목록 삭제, `claude_client.py`·`memory_manager.py`는 `orchestrator/`로 이동, `diff_learner.get_correction_context` 이식. 저장소가 절반으로 줄고 "어느 youtube_script.py인가" 같은 혼동이 사라집니다.
5. **(다음) 채널 결정** — 뉴스레터(스티비), 카드뉴스, 릴스 영상(Muapi)은 코드는 있으나 실전 가동 0건입니다. 운영할 채널만 남기고 나머지는 워크플로우를 끄거나 삭제하는 것이 유지 비용을 줄입니다.
