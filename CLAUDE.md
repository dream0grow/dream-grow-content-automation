# 드림그로우 콘텐츠 자동화 — 프로젝트 컨텍스트

> 이 파일은 새 세션이 자동으로 읽는다. 작업을 이어가려면 `/dreamgrow-resume` 스킬을 호출하라.
> 지난 세션 기록(2026-06~07)은 `docs/HISTORY.md`에 있다.
> 마지막 갱신: 2026-07-07

## 무엇을 만들고 있나

초등 학부모 교육 브랜드 "드림그로우"의 콘텐츠를 **멀티 에이전트 파이프라인**으로 자동 생산·발행한다.
GitHub Actions가 cron으로 카드 저장소를 폴링하고, 사람은 모바일에서 카드 생성·승인만 한다.

흐름: `intake → 리서치 → 키워드 점수화 → ⏸️키워드 승인(자동승인 기본 ON) → 브리프 → 작가↔비평가↔검수 토론 초안 → 검수/평가 → ⏸️발행 승인 → 발행(Threads/스티비)`

**저장소 = 옵시디언 볼트 하나** (노션 철수 완료). 카드는
`vault/파이프라인/활성/원고_<형식>_<카테고리>_<키워드+키워드>_<DG-ID>.md`
(파일명 규칙: 볼트 `SNS 콘텐츠 제작 시스템/00 시스템/03 파일명 규칙.md`, 생성은 `card_filename`),
frontmatter가 라우팅 속성(stage/status/approval_status…), 본문 `## 섹션`이 단계 산출물이다
(`orchestrator/obsidian_state.py`, 볼트 경로 `DG_VAULT_ROOT` 기본 `vault/`). 호출부는 파사드
`orchestrator/state.py`(`from orchestrator import state as store`)만 본다.
**동기화는 GitHub Actions가 `vault/`를 커밋·push하는 git/GitHub 단일 경로다** (노션·Obsidian Sync 아님).
승인·발행 알림은 텔레그램으로 나간다. 이관 경위는 `docs/HISTORY.md`, 기준 사양 `docs/기획/통합기획_v3.md`.

상세 설계: `docs/ARCHITECTURE_V2.md`

## 핵심 ID / 리소스

- 개발 브랜치: **`claude/dreamgrow-orchestrator-review-z4zo4b`** (모든 작업은 여기서, main에 PR로 머지)
- 저장소: `dream0grow/dream-grow-content-automation`
- 카드 저장소: 옵시디언 볼트 `vault/파이프라인/{활성,발행완료}/` (별도 DB 없음, git으로 동기화)
- 볼트 경로 override: `DG_VAULT_ROOT` (기본 `vault/`)
- 알림 채널: 텔레그램 (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`)

## 코드 구조 (`orchestrator/`)

| 파일 | 역할 |
|---|---|
| `run.py` | stage 상태 머신 (DISPATCH) + 고아 청소·실패 재시도. cron이 `python3 -m orchestrator.run` 실행 |
| `state.py` | 저장소 파사드 — 옵시디언 볼트 백엔드를 노출. 호출부(`store`)는 이 모듈만 본다 |
| `obsidian_state.py` | 볼트 카드 저장소 — `vault/파이프라인/` md 카드 읽기/쓰기, 텔레그램+결재함 알림(`notify`) |
| `prompts.py` | 브랜드 보이스/룰북 + 에이전트 프롬프트 (리서치/키워드/브리프/작가/비평가/검수/평가/회고) |
| `agent_dialogue.py` | 작가↔비평가↔검수 토론 루프 + 벤치마킹/후킹 로드 |
| `manus_research.py` | Manus 외부 리서치(전담). 25분 내 결과 없으면 Claude 폴백 |
| `naver_keywords.py` | 네이버 검색광고 API로 키워드 실측 검색량/경쟁도 |
| `publish.py` | publish_ready 카드 발행 (Threads 체인 / 스티비 뉴스레터) |
| `stibee.py` | 스티비 3단계 발행: POST /emails → POST /emails/{id}/content(text/html) → /send |
| `style_learn.py` | AI 원본 vs 사람 수정본 diff → Honcho 문체 학습 |
| `self_improve.py` | 주간 회고 → 프롬프트 개선 큐시트(사람 승인 후 반영) |
| `daily_intake.py` | 매일 새 주제 자동 발제 → intake 카드 생성 (이후 오케스트레이터가 초안까지 자동) |
| `preview.py` | 발행 직전 드라이런: 초안 생성 후 스레드 분할/뉴스레터 HTML 렌더 (시크릿·발행 없이) |
| `cardnews.py` | 초안 → 실사진 오버레이 카드뉴스 PNG (Pretendard, Playwright/Chromium) |
| `thumbnail.py` | 유튜브 썸네일 자동화: 주제 → 문구(기대/증거/의문/공감) 생성·구조분석·디벨롭 → 1280×720 PNG. `data/thumbnail_patterns.md` 주입 |
| `reels_video.py` | 릴스(숏폼) 영상: 릴스 원고 B-roll → Muapi.ai(Open Generative AI 게이트웨이) 장면별 9:16 클립 → ffmpeg 합본 |
| `stock.py` | 실물 스톡 사진 검색 (Pexels/Unsplash, 상업 라이선스) |
| `image_gen.py` | AI 배경 이미지 생성 (OpenAI gpt-image-1 / Google Imagen, 한국인 중심) |
| `cardnews_benchmark.py` | 최근 뜬 카드뉴스 벤치마킹 리서치(Manus/Claude) → `data/cardnews_benchmark.md`, 카드 생성 시 주입 |
| `config.py` | 환경변수 한 곳 관리 |

데이터: `data/benchmark_posts.md`(스레드 7구조·12훅·변주, CSV 분석), `data/hook_patterns.md`(후킹 패턴).
워크플로우: `.github/workflows/orchestrator.yml`(30분 cron), `daily-intake.yml`(매일 07:10 KST 새 주제 발제),
`self-improve.yml`(주간), `test-stibee.yml`(수동 발송 테스트), `test-cardnews.yml`(카드뉴스 실제 생성 테스트),
`test-reels-video.yml`(릴스 영상 실제 생성 테스트).

## 카드뉴스 / 발행 미리보기 (2026-07-01)

- **미리보기(`preview.py`)**: `--topic`으로 초안 생성 후 스레드 분할/뉴스레터 HTML을 파일로 렌더. 발행·시크릿 불필요.
- **카드뉴스(`cardnews.py`)**: 초안 → 슬라이드(표지·본문·마무리) → 실사진 풀블리드 + Pretendard 볼드 오버레이 PNG(1080²).
  - 배경 사진 우선순위(`DG_PHOTO_ORDER`, 기본 `owned,stock,generate`): ①`--photos-dir` 소유 사진
    ②실물 스톡(`stock.py`: `PEXELS_API_KEY`/`UNSPLASH_ACCESS_KEY`) ③AI 생성(`image_gen.py`: `GOOGLE_API_KEY` Imagen
    또는 `OPENAI_API_KEY` gpt-image-1, 한국인 중심) ④그라데이션 폴백.
  - Pretendard는 `ensure_fonts()`가 GitHub에서 받아 설치. Chromium은 로컬 `/opt/pw-browsers` 또는 Actions `playwright install`.
  - 실행/검증: `test-cardnews.yml`(수동, 주제 입력 → PNG 아티팩트). 사진 API는 인터넷 개방된 Actions에서 동작.

## 사람 병목 최소화 (2026-07-01)

사람은 **마지막 발행 승인만** 하도록 설계. 그 앞 단계는 전부 자동:
- **키워드 자동승인 기본 ON** (`config.AUTO_APPROVE_KEYWORD`): 최고점 키워드 자동 채택 → 브리프·초안까지 자동.
  끄려면 `DG_AUTO_APPROVE_KEYWORD=false`.
- **초안 완성 시 텔레그램 알림**: `handle_keyword_approved`가 발행 승인 게이트에서 `notify()` 호출
  → 텔레그램 폰 알림 + 볼트 `_system/review_queue.md` 결재함 기록.
- **매일 자동 발제**: `daily-intake.yml`이 하루 1회 `daily_intake.py` 실행 → 새 주제 카드 생성.
  개수는 `DG_DAILY_TOPIC_COUNT`(기본 1), 대상은 `DG_DEFAULT_AUDIENCE`(기본 "초등 저학년 학부모").

## 환경변수 / GitHub Secrets

필수: (`ANTHROPIC_API_KEY` 또는 `CLAUDE_CODE_OAUTH_TOKEN`)
선택: `DG_VAULT_ROOT`(기본 `vault/`), `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`(알림),
`MANUS_API_KEY`, `HONCHO_API_KEY`, `NAVER_AD_API_KEY`/`NAVER_AD_SECRET`/`NAVER_AD_CUSTOMER_ID`,
`THREADS_ACCESS_TOKEN`/`THREADS_USER_ID`, `STIBEE_API_KEY`/`STIBEE_LIST_ID`/`STIBEE_SENDER_EMAIL`/`STIBEE_SENDER_NAME`/`STIBEE_AUTO_SEND`,
`DG_AUTO_APPROVE_KEYWORD`(기본 ON), `DG_DEFAULT_PUBLISH_TIME`(HH:MM KST 발행 예약 기본값 — orchestrator.yml에서 기본 `21:00`),
`DG_DAILY_TOPIC_COUNT`(기본 1),
`DG_DEFAULT_AUDIENCE`(기본 "초등 저학년 학부모"),
`MUAPI_API_KEY`(릴스 영상 생성 — muapi.ai)/`DG_REELS_VIDEO_MODEL`(기본 `seedance-lite-t2v`)/`DG_REELS_VIDEO_RESOLUTION`(기본 720p)/`DG_REELS_MAX_SCENES`(기본 7)

## 운영 — 자주 하는 작업

카드는 볼트 `vault/파이프라인/활성/`의 md 파일이다. 승인은 카드 frontmatter를 바꾸는 것
(옵시디언/텔레그램). 사람이 바꾼 frontmatter를 cron이 감지해 다음 단계를 돌린다.

- **새 글 만들기**: `vault/파이프라인/활성/`에 카드 생성 (frontmatter `stage: intake`, `status: queued`,
  `format: thread`/`newsletter`/`youtube`(유튜브 롱폼 원고, 콤마 혼합 가능), `audience` 입력).
  매일 발제(`daily-intake`)와 yt_research 사이트 「파이프라인 발제 🚀」도 카드를 만든다.
- **글감 카드 (완성 원고 기반)**: 카드 본문에 `## 📄 글감` 섹션으로 원문을 붙여넣으면
  외부 리서치(Manus/Claude)를 **생략**하고 글감을 근거 자료 삼아 키워드→브리프→초안 진행.
  작가는 글감의 핵심 주장·논리·대사를 보존한 채 채널 형식(스레드 분할·줄바꿈)만 재구성한다
  (모든 재작성 라운드에 글감 유지). 이후 승인·발행 게이트는 일반 카드와 동일.
- **키워드 승인**: 키워드 섹션 확인 → `approved_keyword`에 키워드(또는 부모 고민 문장) 입력 + `approval_status: approved`
- **발행 승인**: 초안/검수 확인 → `review_status: approved`이면 `approval_status: approved` → 자동 발행
- **발행 예약**: 승인하면서 `publish_at`에 `YYYY-MM-DD HH:MM`(KST)을 적으면 그 시각 이후 첫
  cron 실행(30분 주기)에서 발행. 비우면 즉시 발행. `DG_DEFAULT_PUBLISH_TIME`(HH:MM)을 설정하면
  publish_at이 빈 카드 승인 시 다음 도래 시각을 자동 기입(카드에서 수정/삭제 가능).
- **수정 요청**: 카드 `📝 수정 요청` 섹션에 지시 적고 `approval_status: revision_requested` → 재초안
- **orchestrator 수동 실행**: GitHub Actions 탭 → orchestrator → Run workflow (Claude는 권한상 직접 실행 불가, 사용자가 클릭)
- **대량 검토 생성**: `DG_AUTO_APPROVE_KEYWORD=true` → 키워드 자동 채택 → 초안까지 자동 (발행만 사람)

## 알아둘 제약

- Claude(이 세션)는 GitHub Actions 워크플로우를 **직접 실행 못 함**(403). 사용자가 Run workflow 클릭해야 함.
- 볼트 카드는 md 파일이라 Glob/Grep/Read로 직접 읽는다. 본문이 크면 python 슬라이스로 읽기.
- 볼트 동기화는 git 하나뿐 — 여러 워크플로우가 같은 브랜치에 push하므로 `pull --rebase → push`를 재시도한다.
- cron이 정시(00/30분)엔 자주 누락 → `8,23,38,53분`으로 설정함. 불안정하면 수동 실행.
- Manus listMessages는 structured output을 안 줌 → 25분 후 Claude 폴백이 정상 동작(품질 좋음).

## 현재 상태 (세션마다 갱신)

### SNS 콘텐츠 제작 시스템 통합 1+2단계 — 05 리뷰 직접 발행 + 텔레그램 답장 승인 (2026-08-26, 브랜치 `claude/sns-content-auto-publish-qqvfe4`) — ⬅️ 이번 세션 작업

사용자 결정: 파이프라인의 자동 발행을 **SNS 콘텐츠 제작 시스템 폴더 구조로 흡수**한다
(05 리뷰가 곧 결재함 — 별도 카드 이관 없이 그 자리에서 발행). 배경 조사:
SNS 시스템의 원래 흐름 D(05 리뷰/대기 → 리뷰완료+발행시간 → 발행 → 64 발행완료)는
`scheduled_publisher.py`(맥 로컬 하드코딩)가 죽으면서 끊겨 있었다.
- **`orchestrator/sns_publish.py`(신규)**: `05 리뷰/{대기,완료}`에서 `채널: thread|newsletter`
  + **`상태: 리뷰완료`(=발행 승인)** 파일을 찾아 본문 그대로 발행 → `상태: 발행완료`+`발행링크`
  기입 후 `06 제작/64 발행완료/`로 이동 + 텔레그램 통지. orchestrator.yml cron에 배선.
  - 게이트: 검수상태 통과/자동수정완료 아니면 `발행보류`+통지, `발행시간`(KST) 예약
    (비면 기본 21:00 예약 자동 기입), 예약 3일 초과 경과·생성 14일 지난 무시각 승인은
    보류(옛 백로그 오발행 방지), 실행당 최대 5건(`DG_SNS_PUBLISH_MAX_PER_RUN`).
  - 부분 발행 재개(`발행진행` frontmatter), 실패 시 `발행오류`+통지(리뷰완료로 되돌리면 이어서).
  - content_id 있는 열람 사본은 **사본 본문(폰 수정 포함)을 발행**하고 원본 카드를
    published로 동기화(이중 발행 방지). 카드가 이미 발행됐으면 정리만.
  - frontmatter는 원문 보존 줄 단위 수정(콜론 든 주제로 YAML 깨지는 파일 39건 실측 대응).
- **텔레그램 답장 발행 승인**: `script_feedback` triage가 revise/chat에 **publish** 추가
  (`prompts.FEEDBACK_TRIAGE` 3분류 + 상대 시각 환산). "발행해줘"/"내일 21시에 발행" 답장 →
  원고 파일이면 `상태: 리뷰완료`(+발행시간), 카드 ID면 `approval_status: approved`.
  같은 실행에서 sns_publish가 이어 돌아 승인→게이트→발행이 한 사이클에 끝난다.
  알림 문구에 "'발행해줘' 답장=승인" 안내 추가. review_copy 사본 안내문도 갱신
  (사본에서 바로 발행 가능, 안내 인용구는 발행 시 자동 제외).
- **검수 이식**: 폐기한 이관 브랜치에서 수행한 교육윤리 검수 70건을 05 리뷰/대기 원본에
  반영 — 통과 58, 수정필요 11(`검수메모`에 사유), 보류 1. 상세는
  `vault/_system/logs/review_verdicts_2026-08-26.json`. 이제 05 리뷰/대기 스레드/뉴스레터
  238건 중 227건이 검수 통과 상태(상태만 리뷰완료로 바꾸면 발행).
- **이전 작업 폐기**: 05 리뷰→파이프라인 카드 238건 이관(구 커밋 a9b20b7·615d1f8)은
  사용자 결정으로 폐기 — 브랜치를 main에서 재시작(force push). 방향이 반대(카드로 모으기)였음.
- 테스트 14종 신규(test_sns_publish 11, test_publish_approval 3), 전체 171종 통과.
- **2차 확장(같은 세션)** — 알림·대화·3단계 축적까지:
  - **e2e 검증 완료**: 임시 볼트에서 승인 파일 → 게이트 → 실제 split/publish_chain 코드
    → Threads API(mock 4콜) → 발행완료·64 이동 → 텔레그램·결재함 기록까지 전 경로 확인.
  - **알림 확대**: `script_feedback` 알림 필터를 검수 통과(통과/자동수정완료) 원고까지 확장
    (승인 대기 원고도 알림), 승인·보류·오류 상태는 제외(각자 별도 통지). **일일 결재함
    요약**(`send_daily_digest`) 추가 — 매일 8시(KST, `DG_REVIEW_DIGEST_HOUR`) 이후 첫 실행에
    "리뷰 대기 N건(검수 통과 M건)" + 예시 3건 링크. `DG_REVIEW_DIGEST=off`로 끔.
  - **텔레그램 대화 어시스턴트(제한적)**: triage 컨텍스트에 원고 본문(앞 3000자)을 포함 —
    "이 글 어때?", "뭘 보완할까?" 답장에 본문 근거 제안 2~3개로 답한다. 콘텐츠 수정·보완·
    발행 승인 **전용** 가드 명시(원고 무관 요청은 정중히 거절만). `prompts.FEEDBACK_TRIAGE`.
  - **3단계 축적(`sns_publish._accumulate`)**: 발행 성공 시 ①`03 라이브러리/38 주제별
    콘텐츠/<카테고리>/`에 발행본 복사(흐름 D5 — 다음 생성 참고 자산) ②`07 운영/61 성과
    기록/YYYY-MM 발행 기록.md`에 기존 형식 그대로 추가(글 수/플랫폼/링크)
    ③`06 제작/54 발행 캘린더/YYYY-MM 발행 현황.md` 표에 한 줄. 실패해도 발행 성공 유지.
- 테스트 17종 신규(sns_publish 12, publish_approval 5), 전체 174종 통과.
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② 05 리뷰/대기에서 발행할 원고 골라
  `상태: 리뷰완료`(또는 텔레그램 알림에 "발행해줘" 답장) — 그날 21시 자동 발행.
  하루 1~2건 승인 권장 ③ 05 리뷰/완료의 옛 승인 2건은 첫 실행 때 보류 통지가 오면 정리.
- **미착수(선택)**: obsidian_state 경로·스키마 전환(신규 초안 카드 자체를 05 리뷰에 두기)은
  옵시디언-git 동기화와 무관한 내부 저장 위치 문제로, 발행·승인·축적이 이미 통합돼
  실익 대비 위험이 커서 보류(사용자와 논의 후 결정).

### 오즈모 나노 쇼츠 자동 편집 (2026-08-25, 브랜치 `claude/dji-osmo-nano-auto-edit-8m16fx`) — ⬅️ 이번 세션 작업

DJI 오즈모 나노 촬영본을 **로컬(맥/윈도우)에서 초벌 쇼츠로 자동 편집**하는 2층 구조를 추가했다.
실행은 전부 사용자 컴퓨터(원본을 클라우드에 안 올림), 저장소는 규칙 보관·기기 간 동기화 용도.
- **`tools/shorts_edit.py`** (독립 실행, Claude 없이도 동작): 오디오 분석(순수 파이썬 RMS,
  numpy 있으면 가속) → 무음 컷(`--min-silence` 0.9s, 앞뒤 `--pad` 0.3s 여유) →
  **박수=NG 컷**(박수 직전 테이크 제거, `--no-clap`) → 9:16 변환(중앙 크롭 또는 `--fit blur`) →
  ffmpeg 조각 렌더+합본 → **Whisper 자막**(faster-whisper→whisper CLI 폴백, 없으면 생략) →
  자막 굽기(Pretendard 볼드 스타일). 색 보정 없음. 산출물 `<영상명>_shorts/`:
  final.mp4/cut.mp4/subtitles.srt/edit_plan.json(손수정 가능)/notes.md(캡컷 재료).
  `--mode analyze|render(--segment N)|concat|subs|burn|all` — Cowork 45초 제한은 조각 실행으로 대응.
  폴더 입력 시 일괄 처리(SD카드 통째로).
- **스킬 `.claude/skills/dreamgrow-shorts-editor`**: "쇼츠 편집해줘"로 호출 — 컷 계획을 먼저
  보여주고 확인받은 뒤 렌더, srt 수정→burn 재실행 등 피드백 루프. 설치 가이드
  `docs/shorts-edit-setup.md` (Mac: brew install ffmpeg / Win: winget, pip install faster-whisper).
- 테스트 21종 신규(`tools/test_shorts_edit.py` — 컷 로직·박수 판정·크롭 계산·SRT·명령 빌더,
  ffmpeg 불필요). 합성 영상 e2e 검증 완료(무음 제거+NG 컷+1080×1920+자막 굽기).
- **남은 사용자 액션**: ① 브랜치 검토/머지 ② 맥북/윈도우에 ffmpeg + faster-whisper 설치
  (docs/shorts-edit-setup.md) ③ 오즈모 나노 촬영본 하나로 "쇼츠 편집해줘" 라이브 테스트.
  촬영 팁: 일반 색상 프로파일(D-Log 아님)·세로 촬영 권장, NG 나면 박수 한 번.

### 발행 예약 시간 (2026-08-24, 브랜치 `claude/publish-schedule-time-abjf89`)

발행 승인 후 **원하는 시각에 발행**되도록 예약 게이트를 추가했다.
- **frontmatter `publish_at`** (KST, `YYYY-MM-DD HH:MM`): 승인 시 함께 적으면 `handle_publish`가
  그 시각 전엔 발행을 보류(상태 무변경, 다음 cron 재확인). 시각 도래 후 첫 실행에서 발행.
  형식 오류는 조용히 방치하지 않고 `needs_human` + 텔레그램 통지(고치고 status=queued로 복귀).
- **`DG_DEFAULT_PUBLISH_TIME`**(HH:MM): 설정하면 승인 시 publish_at이 빈 카드에
  다음 도래 시각을 자동 기입(카드에 보여 사람이 수정/삭제 가능).
  **orchestrator.yml에 기본 `21:00`(저녁 9시)로 배선** — 시크릿 `DG_DEFAULT_PUBLISH_TIME`으로
  바꾸고, 즉시 발행으로 되돌리려면 시크릿에 `off` 등 형식 밖 값을 넣는다.
- 예약이 걸리면 승인 시점에 "⏰ 발행 예약 완료 — {시각} 이후 자동 발행" 텔레그램 통지.
  승인 요청 안내문·초안 완성 알림에도 예약 방법 추가.
- 코드: `run.py`(`_publish_due`/`_parse_publish_at`/`_next_default_publish_at`, `handle_final_approved`·
  `handle_publish` 게이트), `obsidian_state.py`(publish_at 필드), `config.py`. 테스트 7종 신규, 전체 136종 통과.
- 참고: DG-2026-0023은 사용자가 frontmatter 승인(approval_status/review_status=approved)으로
  2026-08-24 정상 발행 완료(Threads). 승인 조작법이 맞음을 확인.
- 사용자 확정(2026-08-24): 기본 발행 시각 **21:00** → orchestrator.yml env로 배선, main 머지.
  이후 발행 승인만 하면 그날(지났으면 다음날) 21시에 자동 발행된다.

### 텔레그램 답장 대화/질문 감지 — 수정 지시 오인 방지 (2026-08-22, 브랜치 `claude/telegram-ai-conversation-uujj1k`)

사용자가 봇을 대화형 AI로 알고 "이거 파이프라인으로 만들어줘"라고 답장 → 웹훅이 수정 지시
피드백(pending)으로 저장 → 발행 승인 대기이던 DG-2026-0048이 불필요하게 재초안될 뻔한 것을 수리.
- **정리**: 해당 피드백 노트를 `status: answered`로 마감(재초안 차단), 질문이 후보로 저장된
  `_system/candidates/telegram/` 노트 삭제.
- **재발 방지(`script_feedback.py`)**: 피드백 반영 전에 `_triage_feedback`(`prompts.FEEDBACK_TRIAGE`,
  `llm.call_json`)이 메시지를 revise/chat으로 판정. chat(질문·인사·시스템 문의·이미 완료된 요청·모호한
  요청 — 애매하면 chat)이면 원고를 고치지 않고 카드 상태를 근거로 텔레그램 답장(💬) 후 노트를
  `answered`로 마감 + 답변을 노트 본문에 기록. 판정 실패 시 기존 동작(revise) 유지, dry-run은 LLM 미호출.
- 테스트 4종 신규(대화 답장, 카드 디큐 방지, 판정 실패 폴백, dry-run). 전체 127종 통과.
- 봇의 "후보 저장"(candidates) 쪽은 yt_research 저장소 웹훅 소관이라 이 저장소에선 못 고침 —
  일반 메시지(답장 아님)는 여전히 후보로 저장된다.
- **남은 사용자 액션**: ① 이 브랜치를 빨리 머지해야 다음 cron이 DG-2026-0048을 재초안하지 않음
  ② DG-2026-0048 발행은 카드 frontmatter `approval_status: approved`로.

### Open Generative AI 설치 + 릴스(숏폼) 영상 자동 생성 (2026-08-19, 브랜치 `claude/open-generative-ai-setup-jsd2hd`) — ⬅️ 이번 세션 작업

사용자가 요청한 https://github.com/Anil-matcha/Open-Generative-AI (오픈소스 AI 영상 스튜디오,
백엔드=Muapi.ai 통합 게이트웨이)를 파이프라인에 연동했다. **릴스 원고 → 장면별 AI 영상 → 초벌 릴스 MP4**.
- **`orchestrator/reels_video.py`**: 릴스 원고(`05 리뷰/대기/원고_릴스_*.md`)의 B-roll 표
  (타임코드/장면/영어 키워드, `(자체 제작)` 행 제외)를 파싱 → LLM이 장면별 영어 t2v 프롬프트 생성
  (실패 시 키워드 폴백, `--no-llm` 지원) → Muapi API(`POST /api/v1/{model}` → request_id 폴링,
  Open Generative AI와 동일 프로토콜)로 9:16 클립 생성 → ffmpeg로 1080×1920 합본(`reel_draft.mp4`).
  `notes.md`(장면표+내레이션 — 캡컷 마무리 재료)와 `reels_plan.json`도 산출.
  B-roll 표 없는 원고는 `(화면: …)` 지시로 폴백, `--topic`이면 원고 없이 장면 설계부터.
  `--dry-run`은 키/과금 없이 프롬프트만 검증.
- **워크플로우 `test-reels-video.yml`**: 수동 실행 — script(부분 일치)/topic/max_scenes/dry_run 입력
  → MP4·notes·plan 아티팩트 업로드.
- **설치**: GUI 스튜디오는 `bash tools/setup_open_generative_ai.sh`(Mac 로컬 클론+npm setup) 또는
  릴리스 인스톨러. 가이드 `docs/open-generative-ai-setup.md` (Muapi 키 발급→`MUAPI_API_KEY` 시크릿).
- config: `MUAPI_API_KEY`, `DG_REELS_VIDEO_MODEL`(기본 `seedance-lite-t2v` — 비용 낮음, 9:16 지원),
  `DG_REELS_VIDEO_RESOLUTION`(720p), `DG_REELS_SCENE_SECONDS`(5), `DG_REELS_MAX_SCENES`(7 — 과금 상한).
- 테스트 12종 신규(`test_reels_video.py`) — 표 파싱("장면" 단어 포함 행 헤더 오인 버그 수정 포함),
  프롬프트 폴백, Muapi 제출/폴링(mock), ffmpeg 명령, dry-run e2e. 전체 100종 통과.
- **남은 사용자 액션**: ① 브랜치 검토/머지 ② https://muapi.ai 가입 → `MUAPI_API_KEY` 시크릿 등록
  ③ Actions → test-reels-video → 릴스 원고 파일명으로 Run workflow → 아티팩트 MP4 확인
  ④ (선택) Mac에서 `bash tools/setup_open_generative_ai.sh`로 GUI 스튜디오 설치.

### 유튜브 도입부→본문 자동화 + 고전 독서 원고 (2026-08-19, 브랜치 `claude/youtube-script-automation-yqbb4m`, main 머지 완료) — ⬅️ 이번 세션 작업

**문체 학습**: Roam 원고(`vault/raw/Roam-Export-1773035150854/유튜브 만들기_내용포함.md`)의 롱폼
원고 30여 편에서 보이스 프로필 실측 추출 → **`data/youtube_voice.md`** (어미 빈도·도입부 4유형·
전개 패턴·인용 15개+·대표 발췌). 자동 파이프라인 프롬프트에 주입된다.

**도입부→본문 자동화 (`orchestrator/youtube_body.py` + `youtube-body.yml`)**:
- 벤치마킹 시트(분석 탭) **X열 「만든 도입부」에 도입부를 쓰면** 2시간 cron이 감지 →
  행 맥락(S 만든 제목, L 키워드, E~H 시청자 분석, M 디벨롭) 수집 → ①필수 메시지 정리(T08,
  `prompts.YOUTUBE_BODY_MESSAGES`) ②본문·마무리·제작 메모 집필(`prompts.YOUTUBE_BODY`,
  보이스 프로필+HUMANIZE_RULES 주입). **도입부는 사용자 원문 그대로 보존**(코드로 조립).
- 완성 원고는 `vault/파이프라인/활성/` 카드(stage: draft, status: needs_human, format: youtube —
  DISPATCH에 안 걸려 재처리 없음) + `05 리뷰/대기` 사본(script_feedback 텔레그램 핑퐁) 저장.
  카드 파일명은 main의 통일 규칙 그대로(`card_filename` — `원고_YT롱폼_<카테고리>_<키워드>_<DG-ID>.md`).
  시트 되써넣기: 「완성 원고」열(Y)=카드 링크, **「본문」열(Z)=낭독분(본문+마무리, 제작 메모 제외)**.
- 재처리 규칙: `_system/logs/youtube_body_ledger.json`에 행별 `{hash, card}` — **X열을 고치면
  해시가 바뀌어 다음 폴링에 다시 생성**된다. 열은 헤더 이름으로 추적(resolve_columns).
  처리 완료 행의 Y/Z가 비어 있으면(열을 나중에 만든 경우) 카드에서 **백필**(sync_ledger_rows).
- 테스트 12종 신규(`test_youtube_body.py`).

**고전 독서 원고 1건 수동 완성** (시트 13행, 키워드 "초등 고전 독서"):
- T07 → `SNS…/02 분석/24 핵심 내용 및 댓글 분석/초등 고전 독서_핵심 내용 및 댓글 추출.md`
  (영상 9편+커뮤니티 반응 17건 딥리서치. 유튜브 댓글 직접 수집은 프록시 차단 → Threads/Q&A 대체 명시)
- T08 → `SNS…/06 제작/52 원고/초등 고전 독서_필수 메시지 정리.md` (사용자 핵심 메시지:
  '책을 즐기는 사람' 정체성 형성 → 재미 사다리 → 쉬운 고전·소설 중심)
- 완성 원고(도입부 수정본+본문) → `vault/파이프라인/활성/원고_YT롱폼_독서_초등+고전+독서를_DG-2026-0050.md`
  (윤문 스킬 통과). 장부에 카드 참조 시드 완료 — 다음 워크플로우 실행 때 시트 Y13(링크)·Z13(본문) 백필.
- 사용자 완료(2026-08-19): `GSHEET_SA_JSON` 시크릿 등록, 시트에 Z열 「본문」 생성, main 머지.
- **남은 사용자 액션**: Actions → youtube-body Run workflow 1회 실행(또는 2시간 cron 대기)
  → 13행 Y/Z 백필 확인. 이후 X열에 도입부만 쓰면 2시간 내 본문 자동 완성.

### 카드 파일명 규칙 통일 — SNS 파일명 규칙 적용 (2026-08-19, 브랜치 `claude/file-naming-convention-5kv87o`)

`DG-2026-NNNN 제목.md`가 ID순으로만 정렬돼 분류가 안 되던 것을, 볼트의
`SNS 콘텐츠 제작 시스템/00 시스템/03 파일명 규칙.md`에 맞춰
**`원고_<형식>_<카테고리>_<키워드+키워드>_<DG-ID>.md`**로 통일했다.
- `obsidian_state.card_filename` 신설: 형식 라벨(thread→스레드 등), 주제 카테고리
  자동 판별(`topic_category` — 9개 카테고리 키워드 점수, 못 정하면 `기타`),
  키워드는 주제 첫 3어절 `+` 연결. 큐시트 카드는 `큐시트_프롬프트개선_<DG-ID>.md`.
- `create_card(format=...)` 인자 추가(파일명·frontmatter에 반영), ID는 파일명 **끝** —
  채번(`next_content_id`)은 파일명 안의 ID를 어디서든 찾으므로 무영향.
- `script_feedback._resolve_card` glob을 `*DG-ID*.md`로 완화(옛/새 이름 모두 인식).
- 기존 활성 카드 48건 일괄 개명(`tools/rename_cards.py`, `--dry-run` 지원, 재실행 무해).
  라우팅은 frontmatter 기준이라 개명은 파이프라인 동작에 영향 없음.
  단, 과거 텔레그램 알림의 카드 링크(blob URL)는 개명으로 끊어짐(새 알림부터 정상).
- 파일명 규칙 문서에 「파이프라인/활성」 절 추가.
- yt_research 사이트(`lib/pipeline.ts`)도 같은 규칙 적용 완료(그쪽 PR#18 머지,
  `cardFilename` — 파이썬 구현과 출력 일치 검증). 이 저장소는 PR#74로 main 머지 완료.

### 유튜브 썸네일 자동화 — 6단계 방법론 + 구글 시트 직접 읽기/쓰기 (2026-08-19, 브랜치 `claude/youtube-thumbnail-automation-sv47ii`)

사용자의 벤치마킹 6단계 방법론(사용자 교정 반영)을 파이프라인으로 이관. **벤치마킹 썸네일에서 출발**한다.
- **방법론(`data/thumbnail_patterns.md`)**: ①썸네일 보는 사람 분석(상황/고민/욕구/계획)
  ②감정 분석(기대/의문/증거/공감 — 문구+그림 합쳐 10점 배분, 예: 문구 기대9+그림 기대1)
  ③문구+제목 **세트** 구조분석((변수) 분해 + 주의할 점) ④구조에 내 키워드 대입 — **같은 감정을
  증폭**하는 방향으로 변주 6~10개 + 이미지 디벨롭(감정 카테고리별, 효과 없으면 제외 사유)
  ⑤타겟이 '방법'을 원하는 키워드 확장 ⑥검증(상황/고민/욕구/계획 연결+욕구 강도 1~10점,
  근거 없으면 '모델 추정' 표기). 구조 공식 45종(연습 시트에서 실측·주의할 점 포함).
- **구글 시트 연동(`orchestrator/gsheet.py`)**: 서비스 계정(`GSHEET_SA_JSON` 시크릿)으로 분석 탭을
  직접 읽고 쓴다. 설정 가이드 `docs/thumbnail-sheet-setup.md` (사용자 1회 작업 필요).
- **파이프라인(`orchestrator/thumbnail.py`)**: 시트 모드(`--sheet`) — K열 키워드 있고 N열 문구
  디벨롭 빈 행 탐지 → 벤치 썸네일 **비전 OCR**(`llm.call_vision`) → 1~6단계
  (`prompts.THUMBNAIL_ANALYZE/DEVELOP/EXPAND`) → 같은 행 **빈 칸에만** 결과 기입(E~H,I,J,N,O,Q)
  + 확장 키워드 `(자동 확장)` 새 행 추가. 수동 모드(`--topic --benchmark-*`)도 유지.
  최종 픽 1280×720 PNG/JPG 렌더(cardnews 사진 소스 재사용).
- **워크플로우(`thumbnail.yml`)**: 2시간 cron 시트 폴링 + 수동 실행. 아티팩트 + 볼트
  `05 리뷰/대기/썸네일_{주제}.md` 커밋(텔레그램 알림·답장 핑퐁).
- **시트 개편 대응(2026-08-19 2차)**: 열을 헤더 이름으로 해석(`resolve_columns` — 열 이동에도 추적).
  ①J열(영상 문구 분석) 백필 — 기존 벤치마크 행(중복 묶임 행 스킵)에 구조분석+빈 E~H/I/K 채움
  ②확장 행을 시트 끝이 아니라 **벤치마크 행 바로 아래 삽입 + 행 그룹**(벤치 정보 상속,
  L열=새 키워드, M열=키워드로 문구 디벨롭+검증) ③P열=핫비디오로 문구 디벨롭
  (`prompts.THUMBNAIL_HOTVIDEO` — 주제 유지+구조 교체, 시청자 상황/고민/욕구/계획과 연결 업그레이드,
  N/O열 재료 있을 때만).
- **샘플(교정판)**: 시트 12행(영어공부 벤치마크 "영어 문장 한글처럼 읽는 법") → 초등 고전 독서.
  구조 "(원하는 A)을 (쉬운 B)처럼 하는 방법" 대입, 기대 9 증폭 변주 7개("고전을 만화책처럼 읽는
  방법" 등) + 확장 3키워드 + 검증(모델 추정 표기). 볼트 md 교체 + 렌더 검증 완료.
- **확정 렌더 스타일(2026-08-19, 사용자 확정 — 기억)**: 하단 2줄 본문 112px(12자 초과 시 96px),
  좌상단 킥커 46px 연두(#a8e063) "현직 초등 교사가 알려주는"(`DG_THUMB_KICKER`), 도현체+스트로크 진하게,
  하단 스크림. 피부 리얼리즘 프롬프트(REALISM 상수 — pores/vellus hair/candid/iPhone photo 등) 항상 덧붙임.
  참조 이미지: `data/thumbnail_assets/<키워드>/`에 실제 책 표지 등을 넣으면 gpt-image-1 edits/Gemini로
  그 이미지를 반영해 장면 생성 (README 참고).
- 테스트 86종 통과(test_thumbnail.py).
- **남은 사용자 액션**: ① 브랜치 검토/머지 ② `docs/thumbnail-sheet-setup.md` 따라 서비스 계정
  만들고 `GSHEET_SA_JSON` 시크릿 등록 + 시트를 서비스 계정 이메일에 편집자 공유
  ③ 이후 시트에 키워드만 적으면 2시간 내 자동 처리 (또는 Run workflow 즉시 실행).
- **대화형 스킬**: `.claude/skills/dreamgrow-thumbnail` — "썸네일 만들어줘"로 호출.
  ①참조 이미지 파일명 확인(data/thumbnail_assets, 없으면 업로드 안내) ②리얼리즘 프롬프트 필수
  ③벤치마킹 이미지 요청 → 생성·렌더·전송 → 피드백 반영 반복. 파이프라인과 같은 엔진 사용.
- **다음 예정**: 썸네일 이미지 만들기 고도화 후 → **도입부 문장 생성** 단계 추가 (사용자 지시).

### 글감 카드 — 완성 원고를 스레드로 재구성하는 입구 (2026-08-19, 브랜치 `claude/child-sharing-behavior-wzu82g`) — ⬅️ 이번 세션 작업

사용자가 완성 원고(글감)를 주면 그걸 **토대로** 스레드를 뽑는 파이프라인 입구를 추가했다.
- **동작**: 카드 본문 `## 📄 글감` 섹션이 있으면 `handle_intake`가 리서치를 생략하고 keyword로 직행.
  키워드 점수화·브리프 컨텍스트에 글감 포함(`read_sections_by_prefix`에 `📄 글감` 추가).
  `run_draft_dialogue(source_material=...)`가 작가 프롬프트에 `[글감 - 이 글이 초안의 토대]`
  블록을 **모든 작가 호출**(첫 집필+비평/윤리 재작성)에 주입 — 핵심 주장·대사 보존, 새 사례 창작 금지.
  `prompts.WRITER`에 `{source_block}` 플레이스홀더 추가.
- **첫 글감 카드**: DG-2026-0048 (달라고 하기 전에 물건 나눠주는 아이 — 물건 말고 마음으로 관계 맺기,
  `format: thread`). 글감은 이번 세션에서 윤문(im-not-strange-ai 등급 A)까지 마친 원고.
- 테스트 61종 통과(신규 2: intake 리서치 생략, 재작성 라운드 글감 유지).
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② orchestrator Run workflow 실행(또는 cron 대기)
  → DG-2026-0048이 글감 기반으로 초안 생성 → 발행 승인만 하면 Threads 발행.

### 에이전트 OS 점검 + 텔레그램 핑퐁 전면 확장 (2026-07-13, main 머지 완료) — ⬅️ 이번 세션 작업

- **daily-intake 7일 연속 실패 수리** (#58): 워크플로우가 미설정 시크릿을 빈 문자열로 넘겨
  `int('')` 크래시(2026-07-07~12 전건 실패). `daily_intake.py` env 파싱을 `or` 폴백으로 교체.
- **새 카드 접수 텔레그램 통지** (#59): `handle_intake`가 `🆕 새 카드 접수`(ID+주제)를 notify —
  매일 발제·사이트 발제 모두 커버. 생성→초안→발행 전 과정이 폰 알림으로 이어진다.
- **핑퐁 전면 확장 — 파이프라인 카드도 답장 수정** : `script_feedback.py`가 피드백 target의
  카드 ID(DG-YYYY-NNNN)를 인식, 활성 카드에 `📝 수정 요청` 섹션 기록 + `approval_status:
  revision_requested`로 디큐(여기선 LLM 안 부름 — run.py `handle_revision_requested`가 재초안).
  yt_research 웹훅도 카드 ID 추출 추가(그쪽 PR#15). 즉 **스레드/뉴스레터 카드(→카드뉴스),
  유튜브 롱폼·스레드·릴스 원고 파일 전부 텔레그램 답장으로 수정**된다.
- **알림 대상 확대**: `05 리뷰/대기` 알림을 youtube-script 한정 → 전 형식으로. 폭주 방지로
  비-youtube는 frontmatter 생성일 `DG_ANNOUNCE_MAX_AGE_DAYS`(기본 7일) 이내만, `상태: 발행완료`
  등은 제외. 빈 YAML 값(`검수상태:`)이 None으로 파싱돼 걸러지던 버그도 수리(`or ""`).
- 사용자가 `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` 시크릿 설정 완료(2026-07-13) — 알림 라이브.
- **알림에서 바로 읽기**: `obsidian_state.notify()`가 카드 GitHub blob 링크를 항상 첨부 —
  텔레그램에서 누르면 카드가 열린다.
- **초안 열람 사본**(`orchestrator/review_copy.py`): thread/newsletter 초안 완성 시
  `05 리뷰/대기/{스레드|뉴스레터}_{주제}.md`(기존 파일명 규칙)로 사본 저장 → script_feedback이
  링크 포함 알림. frontmatter `content_id`로 원본 카드를 가리켜, 이 파일명으로 온 피드백은
  **카드 재초안으로 라우팅**(사본 직접 수정은 발행에 반영 안 됨 — 파일 상단에 경고 주석).
  재초안 시 같은 파일명으로 덮어써 항상 최신 초안을 비춘다. 발행 원본은 여전히 카드다.
- **소크라테스 질문 맥락 고정**(`vault_pipeline/socrates.py`, `.claude/agents/zk-socrates.md`):
  "교실 0.1x/제도 10x" 강제 프레임 제거. 노트의 주제 영역(비즈니스/교육/방법론)을 먼저 파악해
  **그 주제 안에서** 전제 검증·반례와 경계·재정의/다음 단계를 묻는다(맥락 갈아끼우기 금지).
- 테스트 59종 통과(신규: intake 통지 1, 카드 핑퐁 2, 알림 확대 2, 사본 라우팅 1, 사본 내보내기 1 등).
- 미결: DG-2026-0001 발행 승인 대기(사용자), DG-2026-0002 큐시트 승인 대기.

### 유튜브 롱폼 원고 자동화 (2026-07-13, 병렬 세션, main 머지 완료)

`format: youtube` 카드가 들어오면 리서치→키워드→브리프는 기존 그대로 타고, 초안 단계에서
**유튜브 롱폼 원고**(제목·썸네일 문구 + 30초 도입부 + 타임스탬프 본문 + 제작 메모)를 자동으로 쓴다.
신규 `orchestrator/youtube_script.py` + `prompts.YOUTUBE_SCRIPT`(HUMANIZE_RULES 주입) + 테스트 6종(전체 52종 통과).
- **인계 경로**: 원고를 `05 리뷰/대기`에 사이트와 동일한 frontmatter(`type: youtube-script`,
  `검수상태: 대기`)로 저장 → 기존 `script_feedback`(같은 orchestrator.yml 실행)이 파일명 포함
  텔레그램 알림 → 답장하면 수정 반영 핑퐁. **발행 게이트 없음** — 유튜브 원고의 종착지는 촬영.
- **유튜브 전용 카드**: 원고 인계 후 `stage: published, status: done`으로 완료 + 통지.
  혼합(`thread, youtube`)이면 유튜브 원고는 별도 저장하고 thread/newsletter는 기존 승인 게이트 진행
  (유튜브 생성 실패 시 통지 후 thread 흐름 계속).
- **발제 입구**: yt_research 사이트 「파이프라인 발제 🚀」에 "유튜브 원고 🎬" 옵션 추가
  (`lib/pipeline.ts` format: youtube). 카드 직접 생성 시에도 `format: youtube`면 동일 동작.
- 원고 길이는 `DG_YT_SCRIPT_MINUTES`(기본 10분, 분당 300자 환산).
- **남은 사용자 액션**: 유튜브 발제 1건으로 라이브 확인.

### 원고 수정·보완 핑퐁 오케스트레이터 쪽 완성 (2026-07-10, 브랜치 `claude/claude-md-telegram-pingpong-hfb443`)

yt_research 사이트가 만든 롱폼 원고(`vault/SNS 콘텐츠 제작 시스템/05 리뷰/대기/원고_*.md`)와
사용자의 텔레그램 답장을 잇는 핑퐁의 **오케스트레이터 쪽 나머지 절반**을 구현했다.
사이트 수신부(웹훅 → `_system/feedback/` pending 노트 저장)는 yt_research에 이미 있었다.
신규 모듈 `vault_pipeline/script_feedback.py` + 테스트 7종(전체 43종 통과).
- **① 초안 완성 알림**: `05 리뷰/대기`의 `type: youtube-script` + 검수 대기 원고를 찾아
  **파일명을 포함한** 텔레그램 메시지를 보낸다. 사용자가 이 메시지에 답장하면 사이트 웹훅이
  파일명을 추출해 피드백 노트를 만든다. 중복 알림은 `_system/logs/script_feedback_ledger.json`로 차단.
- **② 피드백 반영**: `_system/feedback/`의 `type: feedback, status: pending` 노트를 읽어 대상 원고를
  `llm.call_writing`(+`SCRIPT_REVISE` 프롬프트, HUMANIZE_RULES 주입)로 수정하고, 노트를
  `status: applied`(대상 없음/유실 의심 시 `error`)로 갱신 → 재처리 방지. 반영 완료를 텔레그램 통지.
- **안전장치**: 원고 수정은 **프론트매터 원문을 그대로 보존**하고 본문만 교체(끝에 HTML 주석 감사 흔적).
  수정본이 200자 미만이거나 원본의 50% 미만이면 내용 유실로 보고 반영하지 않고 `error`로 남긴다.
- **폴더/스키마 정합**: `VAULT_SCRIPT_PATH`(기본 `SNS 콘텐츠 제작 시스템/05 리뷰/대기`)·
  `VAULT_FEEDBACK_PATH`(기본 `_system/feedback`)를 사이트 lib/vault.ts와 동일 기본값으로 맞췄다.
- **배선**: `orchestrator.yml`(15분 cron)에 `python3 -m vault_pipeline.script_feedback` 단계 추가
  (기존 볼트 커밋·push 재시도 루프가 원고/피드백 변경도 함께 동기화). 수동 stage 실행 시엔 건너뜀.
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② yt_research가 원고를 저장하는 실제 폴더가 기본값과
  다르면 양쪽 `VAULT_SCRIPT_PATH`를 같은 값으로 맞출 것 ③ orchestrator Run workflow로 라이브 반영.

### 플라우드 파이프라인 "새 녹음 없음" 오판 수리 (2026-07-10, 브랜치 `claude/plaud-mcp-setup-6j07l1`)

텔레그램에 "처리할 새 녹음 없음"만 오던 원인 3개를 수리. vault_pipeline 테스트 20종 통과(신규 6종).
- **근본 원인**: 플라우드에서 **전사 안 된** 녹음은 `get_transcript`가 `[]`를 반환하는데, 이걸 유효
  전사로 취급 → "짧아서 생략"으로 장부에 **영구 기록**(18분짜리 포함 6건 소실, 산출물 0건이었음).
  `plaud_client._transcript_text()`가 응답에서 실제 발화만 추출, 빈 구조는 "전사 대기"로 분류해
  장부에 안 올림 → 앱에서 전사하면 다음 실행에 자동 처리.
- **기아 수정**: 전사 대기 녹음이 quota(`--max`)·fetch limit을 선점하지 않게 하고, todo를
  **오래된 것부터** 처리(최신 메모가 옛 녹음을 7일 창 밖으로 밀어내던 문제).
- **알림 정확화**: `telegram_notify.briefing(pending=)` — "⏳ 전사 대기 N건 — 앱에서 전사하면
  다음 실행에 자동 처리" 표시. 잘못된 장부 6건 리셋(ledger 비움).
- **운영 메모**: 이 파이프라인은 **플라우드 앱에서 전사가 돌아간 녹음만** 가공할 수 있다.
  자동 전사 설정을 켜두거나, 녹음 후 앱에서 전사를 실행해야 한다.
- **후속 수리 2건**: ① plaud-pipeline·vault-agents 워크플로우에 Claude Max CLI 폴백 배선
  (ANTHROPIC_API_KEY 시크릿이 비어 있어 FileNotFoundError('claude')로 전건 실패하던 것,
  orchestrator.yml 패턴 이식). ② 텔레그램 알림에 **녹음별 산출물 상세**(📼 녹음명 + 메모 제목
  최대 5개 + 🔑키워드 + 💬의견)와 저장 위치(`vault/제텔카스텐/{1.메모,2.키워드,3.의견}`) 표시 —
  `process_recording`이 `detail`을 반환, `briefing(details=)`가 렌더. 제목은 **GitHub 노트로
  열리는 링크**(텔레그램 HTML 모드, `note_url()` — blob/main URL). push 완료 후 링크가 열린다.

카드 저장소를 노션에서 완전히 걷어내고 옵시디언 볼트 하나로 고정, 동기화는 git/GitHub 단일 경로. 전체 27종 통과.
- **백엔드 일원화**: `state.py` 파사드를 옵시디언 전용으로(이중 백엔드·`DG_STATE_BACKEND` 폐기).
  `notion_state.py`·`notion_media.py` 삭제. 호출부 별칭 `notion_state`→`store`로 전 모듈 개명.
- **config**: `NOTION_*`·`require_notion` 제거. 저장소=볼트(`DG_VAULT_ROOT`), 알림=텔레그램.
- **워크플로우**: orchestrator·daily-intake·self-improve·backfill의 `NOTION_*` 시크릿 제거,
  볼트에 쓰는 워크플로우 전부에 **git 커밋·push 단계**(경합 재시도)와 `pyyaml`·`contents:write` 추가.
  test-cardnews의 노션 저장(`--notion-page`) 제거 → PNG 아티팩트만. cardnews의 노션 업로드 경로 삭제.
- **문서**: CLAUDE.md·ARCHITECTURE_V2·PLAUD_INTEGRATION·dreamgrow-resume·plaud-zettel의 노션 서술을
  볼트/Git로 교체. 통합기획 v3의 D-29(동기화=Obsidian Sync)를 **git/GitHub 유일**로 개정.
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② Actions Secrets에서 `NOTION_*` 삭제(선택) +
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` 설정 확인 ③ 진행 중이던 노션 카드가 있으면 볼트로 옮긴 뒤 실행.

### 오케스트레이터 안정성·토큰 수리 (2026-07-07, 브랜치 `claude/dreamgrow-orchestrator-review-z4zo4b`)

무개입 자동화를 깨던 "조용히 멈추는 구멍" 봉합 + 토큰 절감. 전체 테스트 25종 통과(신규 `orchestrator/test_run.py` 9종).
- **A1 수정 요청 데드엔드 해소**: `approval + revision_requested`를 처리하는 `handle_revision_requested`
  추가(DISPATCH 배선). 사람이 `📝 수정 요청` 섹션에 지시를 적고 `approval_status=revision_requested`로
  바꾸면 → keyword_approval로 되돌려 지시를 작가에게 되먹여 재초안(빈 키워드면 키워드 게이트로).
  `run_draft_dialogue(extra_directive=...)`로 첫 집필부터 반영.
- **A2 침묵 차단 해소**: `handle_final_approved`가 검수 미통과인데 승인된 경우 로그만 남기던 것을,
  `needs_human`+`approval_status=blocked`로 디큐하고 사유·다음 행동(재승인/재초안)을 `notify()`로 통지.
- **A3 실패 침묵 해소**: `run()`의 예외를 `_handle_failure`로 처리 — intake/research/keyword는 1회 자동
  재시도(`last_error`에 `[자동재시도]` 표식), 재시도 후에도 실패면 `failed`+통지. keyword_approval/approval은
  status 무시 쿼리라 표식으로 1회 재시도 후 `approval_status=failed`로 디큐. **publish_ready는 부분발행
  중복 위험으로 재시도 제외**(즉시 통지).
- **A4 고아 카드 청소기**: `run()` 시작 시 `_sweep_stale_running` — brief/draft가 running으로
  `DG_STALE_RUNNING_MINUTES`(기본 60) 넘게 멈추면 keyword_approval/approved로 재큐.
- **A5 스레드 글 유실 방지**: `split_posts`가 500자 초과 문단을 `[:500]`으로 잘라 버리던 것을
  문장 단위(`_split_sentences`) 이월 분할로 교체 — 글이 유실되지 않음.
- **A6 발행 성공 통지**: Threads/뉴스레터 발행 성공 시 링크와 함께 `notify()`(폰에서 사이클 종료).
- **B1 토큰**: `prompts._load_learned_overlay`에 `@lru_cache` — 카드당 10여 회 Honcho 원격 질의를 1회로.
- **B2 토큰**: 글 평가 총점이 `DG_RUBRIC_SKIP_QUALITY`(기본 45/50) 이상이면 2차안(전문 재작성) 생략.
- **모델 ID 고정(완료)**: `config.py`·`photo_judge.py` 기본 유틸리티 모델을 실재하지 않던
  `claude-sonnet-4-6` → **`claude-sonnet-5`**로 교체. (글쓰기는 `claude-opus-4-8` 유지)
- **B4 CLAUDE.md 대청소(완료)**: 상단을 옵시디언 전환 현행으로 교체, 개발 브랜치 갱신,
  과거 세션 로그(2026-06-13~07-06)를 `docs/HISTORY.md`로 이관(311→149줄).
- **A8 볼트 push 경합 방지**: orchestrator·plaud·vault-agents·cardnews-benchmark 워크플로우의
  `pull --rebase → push`를 5회 재시도 루프로 감싸 동시 push 실패(non-fast-forward)를 흡수.
- **B3 컨텍스트 선별 주입**: `read_sections_by_prefix`(두 백엔드+파사드) 추가. 키워드/브리프 단계에
  카드 본문 전체 대신 리서치·키워드 섹션만 주입 — A1 재초안 시 누적된 옛 초안 재주입을 막아 시너지.
- **B5 무거운 참고자료 첫 집필만**: 후킹·벤치마킹(13KB+)을 v1에만 넣고 비평/윤리 재작성 호출에선 제외.
  `get_style_context`에서 벤치마크 분리, `run_draft_dialogue(benchmark=...)`로 전달.
- **A7 완료(노션 철수 후)**: 학부모 발행 카드(`stage: published`) 원자 메모 환류를
  `vault_pipeline/feedback.py`에 추가(`find_published_pipeline`). 문체 학습은 발행 시 style_learn이
  이미 하므로 atomize만 수행(author 이한결·source_type own_content). 발행완료+본문 100자↑ 카드만,
  장부(feedback_ledger)로 중복 방지 — 잘못된 카드 유입 차단.
- **테스트**: 전체 30종 통과(신규 `test_run.py` 10종, `test_obsidian_state` B3 1종, `test_feedback` A7 3종).
- **남은 사용자 액션**: ① 이 브랜치 검토/머지 ② orchestrator Run workflow로 라이브 반영.

> 지난 세션 기록은 `docs/HISTORY.md`로 이관했다 (2026-06-13 ~ 2026-07-06).

## 한국어 윤문 스킬 — 제3자 노출 문구는 무조건 적용 (필수)

제3자에게 보여주는 **모든 한국어 문구**를 작성·수정했다면, 발행·커밋 전에 반드시 아래 윤문 스킬을 거친다.
대상 예시: 스레드 글, 카드뉴스, 뉴스레터, 영상 스크립트, 강의 스크립트, 홈페이지·랜딩 카피라이팅,
앱 화면 텍스트(버튼·안내·오류 메시지 등 UI 문구), 상세페이지, SNS 게시물.
제외: 코드 주석, 내부 문서, 커밋 메시지 등 사용자 본인만 보는 텍스트.

- **기본**: `/im-not-strange-ai` — Sunny 문장 규칙 포함 (`.claude/skills/im-not-strange-ai`)
- **대안**: `/humanize-korean` 또는 `/humanize` (`.claude/skills/humanize-korean`)
- 8,000자 초과·정밀 검증이 필요하면 `--strict` (5인 파이프라인)
- 원칙: 의미·사실·수치는 한 글자도 바꾸지 않고 문체·리듬·표현만 다듬는다

스킬·에이전트는 이 저장소 `.claude/skills/`·`.claude/agents/`에 동봉되어 있다.
출처: https://github.com/epoko77-ai/im-not-ai · https://github.com/itssosunny/im-not-strange-ai

**자동 파이프라인에도 적용 (2026-07-01)**: GitHub Actions에서 도는 orchestrator는 Claude Code 스킬을
직접 못 쓰므로, 같은 룰북을 `prompts.py`의 `HUMANIZE_RULES` 상수로 요약해 작가(WRITER)·카드뉴스(CARDNEWS)
프롬프트에 주입했고, 비평가(CRITIC)에 "AI 티" 평가 기준(5번)을 추가해 토론 루프에서 탐지→재작성이 돌게 했다.
스레드·뉴스레터·카드뉴스 자동 초안 전부에 적용된다.
