# 지식 선순환 로드맵 — 코드 정리 + 제텔카스텐↔콘텐츠 순환 배선

> 작성 2026-09-19 · 브랜치 `claude/knowledge-cycle-roadmap-2026-09` · **이 문서가 이 주제의 진행 기준(단일 진실원천)이다.**
> 어떤 세션·어떤 AI(Claude, Codex, Gemini 등)든 이 작업을 이어받을 때는 §0을 먼저 읽고, 끝낼 때 §3 체크박스와 §6 진행 로그를 갱신한다.
> 근거 문서: `CLAUDE.md`(운영 현황), `vault/CLAUDE.md`(볼트 헌법), `docs/ARCHITECTURE_V2.md`, `docs/기획/통합기획_v3.md` §4(역방향 4단 관문), `docs/기획/MASTER_PLAN.md` Phase B·E.

---

## 0. 이 문서 사용법 (다중 세션·다중 AI 공통 규칙)

1. **시작**: §3에서 미완 항목(`- [ ]`) 하나를 고른다. 의존 항목이 끝나지 않았으면 고르지 않는다. §6에 `착수: 날짜 / 항목 / 세션·AI 이름`을 적는다.
2. **브랜치**: 이 브랜치(`claude/knowledge-cycle-roadmap-2026-09`)에서 작업한다. 병렬 세션은 하위 브랜치 `claude/kc-<phase>-<slug>`를 파고, 끝나면 이 브랜치로 합친다. Phase 단위로 main에 PR.
3. **완료**: 체크박스를 채우고 옆에 커밋 해시를 적는다. §6에 `완료: 날짜 / 항목 / 검증 방법`을 적는다. "완료 판정" 조건을 실제로 확인하지 않았으면 체크하지 않는다.
4. **결정**: 사용자(이한결) 결정이 필요한 것은 §5 "미결"에 적고 **임의로 정하지 않는다.** 사용자가 확정하면 "결정 레지스트리"로 옮긴다.
5. **안전**: 볼트 헌법(`vault/CLAUDE.md`) 준수. 삭제·대량 이동·rename은 dry-run → 사용자 승인 → git 커밋 → 실행. 시크릿은 절대 커밋하지 않는다(`tools/vault_secret_scan.py`).
6. **문체**: 제3자 노출 한국어 문구는 `/im-not-strange-ai` 윤문을 거친다. 이 문서는 내부 문서라 예외.
7. **CLAUDE.md**: 현황 요약 4~5줄만 갱신하고, 상세는 전부 이 문서에 쓴다.

---

## 1. 목표와 불편 (사용자 원문 요지, 2026-09-19)

**최상위 목표 = 지식 선순환**
① 제텔카스텐에 나만의 지식을 쌓고 창조한다 → ② 유튜브·스레드·릴스·쇼츠 콘텐츠를 만든다 → ③ 만들면서 생긴 지식을 다시 제텔카스텐에 쌓는다 → ④ 그 지식으로 다시 콘텐츠를 만든다. 플라우드 전사(회의·일상 인사이트)도 이 순환의 입력이어야 한다. 유튜브는 yt_research로 타 영상을 수집·분석한 뒤 만드는 경우도 있다.

**불편 6가지** (5번이 "가장 큰 문제")
1. 사람 병목으로 SNS 콘텐츠를 잘 못 올린다.
2. 병목 원인은 퀄리티. 전문성이 중요해 틀린 이야기·저품질은 절대 올리지 않는다. 계속 수정해야 한다.
3. 맥북이 멈추면 작업이 멈춘다. 24시간 도는 에이전트 팀을 원한다. 집의 윈도우 노트북을 리눅스로 바꿔 서버로 쓸까 고민 중.
4. 맥북·폰·윈도우 어디서든 이어서 작업하고 싶다. 옵시디언은 git 동기화+텔레그램 구조에서 사실상 불필요해졌지만, git UI와 commit 과정이 불편하다.
5. SNS 콘텐츠와 제텔카스텐이 선순환하지 않는다. 만든 콘텐츠가 지식이 되지 않고, 지식이 창조적으로 재활용되지 않는다.
6. 플라우드 전사문의 인사이트가 지식으로 정리되지 않고 SNS에도 활용되지 않는다.

**추가 요청 (2026-09-19 2차)**: 촬영 때 원고와 다르게 말하는 경우가 많다. 발행된 영상 최종본(유튜브·인스타)에서 실제 발화 스크립트를 뽑아 원고와 대조하고, 더 나은 방향으로 원고를 업그레이드하는 AI 학습을 넣는다. 뽑은 발화 스크립트는 제텔카스텐 구조에 저장한다. → §4.

---

## 2. 진단 요약 (2026-09-19 실측, 코드·볼트·yt_research 전수 조사)

### 2-1. 코드 세대 — 세 세대가 한 저장소에 공존

| 세대 | 위치 | 규모 | 상태 |
|---|---|---|---|
| 1세대 (2026-04) | 루트 `.py` 23개, `agents/`, `scheduled/`, `main.py`, `skills-draft/`, `apple_notes_raw/`(723 json), `pdf_output/` | 약 6,300줄 | 워크플로우 17개·스킬 어디서도 미참조. `/Users/lhg/...` 절대경로 20개. 외부 볼트 `초생산` 전제. 살아 있는 건 `claude_client.py`·`memory_manager.py`·`diff_learner.py` 3개뿐이며 패키지가 `sys.path`로 끌어다 씀 |
| 2세대 (2026-06~) | `orchestrator/` | 약 10,100줄 (테스트 1,674) | 실제 운영 본체. 워크플로우 17개 전부 여기서 시작 |
| 2.5세대 (2026-07~) | `vault_pipeline/` | 약 4,100줄 (테스트 1,127) | 플라우드·피드백·텔레그램·소크라테스. orchestrator와 **양방향 import**(함수 안 deferred import 6곳으로 순환 회피). 자체 config 없음 |
| 별도 저장소 | `yt_research` (Next.js 14, Vercel, Supabase) | — | GitHub Contents API로 볼트에 직접 씀. 텔레그램 웹훅 수신부 |
| 타 채널 | `youtube/` | 1,289줄 | 10x인생 채널 소유. 불가침 |

### 2-2. 중복 실태

| 항목 | 벌 수 · 위치 |
|---|---|
| frontmatter 파서 | `vault_io.parse_frontmatter` = `obsidian_state._split` (정규식·예외 처리 동일). 루트 스크립트에 손파서 5벌 더 |
| 장부 JSON load/save idiom | 7벌 (`vault_io`, `feedback`, `script_feedback`, `reels_recommend`, `telegram_assistant`, `script_learn`, `youtube_body`) |
| 문체 학습 프롬프트 | 4벌(`vault_pipeline.prompts.STYLE_DIFF`, `orchestrator.prompts.STYLE_DIFF`, `script_learn.analyze`, 루트 `diff_learner`), 저장소 3곳(`style_lessons.md`·Honcho·카드 섹션). 두 벌이 같은 Honcho 세션에 씀 |
| `DONE_STATES` | 3벌, 서로 다른 집합 |
| `05 리뷰/대기` 경로 상수 | 5벌 |
| `save_to_review` | `youtube_script` vs `extra_formats` 근사 복사 |
| `_file_token` | `youtube_script`·`thumbnail` 바이트 동일 |
| review_queue.md 쓰기 | 두 모듈, 두 형식 |
| GitHub blob URL 생성 | 2벌, 환경변수 이름 계열도 다름 |
| **yt_research와 손복제** | 카드 파일명 규칙·카테고리 표·keyword slug·content_id 채번·프론트매터 스키마(**`publish_at` 드리프트 이미 발생**)·텔레그램 전송·카드ID 정규식·피드백 노트 스키마·브랜드 룰북(약 6곳)·벤치마크 채점·시트 열 해석. 두 시스템이 **같은 시트 탭**과 **같은 `_system/feedback`**에 동시에 씀 |

### 2-3. 지식 순환 실측 — 코드에 없다

`orchestrator/`에 "제텔카스텐"이라는 문자열 자체가 없다.

| 방향 | 실측 |
|---|---|
| 지식 → 콘텐츠 | 활성 카드 90개 중 제텔카스텐 참조 **0**. 05 리뷰/대기 448건 중 제텔 링크 17건(16건은 2026-04-09/10). 글감→원고 8건, 전부 4월 |
| 콘텐츠 → 지식 | 발행 카드 4개에서 메모 19개(2026-08-21~29)뿐. 전부 `원출처_추적: 필요`로 격리된 채 방치. `feedback_ledger` 4건 모두 `lessons: 0` |
| 플라우드 → 지식 | 노트 490개(메모 273·키워드 100·의견 105·사례 11), **전부 7월 녹음**. 8월 이후 0. 앱 미전사 6건 대기(9/3~9/7) |
| yt_research → 지식 | 0. `02 분석` 15건을 제텔카스텐이 참조한 적 없음 |
| 역방향 관문 `_system/candidates/` | **0건** (헌법이 정한 유일한 교차 쓰기 지점) |
| `used_in` 역링크 | **0건** |
| 문체 학습 산출 `_system/style_lessons.md` | 파일 없음 |

세 반쪽 순환(플라우드→지식 7월, 발행→지식 8월, 글감→원고 4월)이 각각 한 번씩 작동했고 시기가 겹친 적이 없다. 2026-09-19 현재 셋 다 멈춰 있고, 콘텐츠 공장은 웹 리서치만으로 매일 돈다.

### 2-4. 사람 병목 실측

| 항목 | 수치 |
|---|---|
| 활성 카드 `needs_human` | 59 / 90 |
| `05 리뷰/대기` : `05 리뷰/완료` | 448 : 2 |
| 소크라테스 새벽 질문 답변 | 0 / 49일 (147문항) |
| 발행까지 간 카드 | 4 / 90 (`발행완료/` 폴더 비어 있음, 발행 카드가 `활성/`에 남음) |
| `_system/lessons.md` · `values.md` | 예시 1줄 · `TODO(이한결)` 그대로 |
| 60일 볼트 커밋 중 장부·로그만 바뀐 것 | 1,214 / 1,533 (**79% 소음**) |

### 2-5. 원인 두 줄

1. **작가가 사용자의 지식을 읽지 않는다.** 브리프 재료 = Manus/Claude 웹 리서치 + 후킹 패턴 + 벤치마크 글. 구술 노트 389·의견 119·주장 31·주제별 라이브러리 293·본인 스레드 아카이브 CSV는 프롬프트에 들어간 적이 없다. → 초안이 "일반 육아 글"이 되고 전문성은 사람이 수정으로 채운다(불편 2). 품질 게이트는 점수표(50점·100점)뿐, "이 주장의 출처가 어디냐"를 묻는 관문이 없다.
2. **승인이 git 안의 YAML 편집이다.** 매일 발제는 승인 속도와 무관하게 카드를 만든다. 통합기획 v3 Phase B "텔레그램 인라인 버튼 승인"은 설계만 있고 미구현. 텔레그램 답장은 15분 cron 폴링. → 대기열만 자란다(불편 1·4).

### 2-6. 장단점

**장점**: 상태 머신이 견고(고아 청소·자동 재시도·부분 발행 재개·발행 예약·시크릿 스캔). Threads·스티비·텔레그램·시트·뷰트랩 연동이 실제 작동(120일간 orchestrator 커밋 88건). 저장소가 md라 어디서든 읽힘. 볼트 헌법(권한 매트릭스·`_ai` 딱지·사례 신호등·`own_content` 순환참조 플래그)은 설계로서 드물게 좋다.
**단점**: 세 세대 공존. 순환 import. **테스트가 CI에서 돌지 않음**(pytest가 requirements에도 없음). yt_research와 규칙 드리프트 시작. git 소음 79%. 저장소 루트에 `.obsidian`이 하나 더 있어 코드 폴더가 볼트로 열린 흔적. 플라우드 triage는 교사 글감만 판정(학부모 SNS 씨앗 승격은 수동 스킬에만).

### 2-7. 24시간·기기 문제의 실체

파이프라인 본체는 이미 GitHub Actions에서 맥북 없이 돈다. 맥북에 묶인 것: ① 대화형 Claude Code 세션 ② 뷰트랩 쿠키 동기화(launchd) ③ 쇼츠 렌더링(ffmpeg·Whisper) ④ Aside 브라우저. 리눅스 노트북이 해결하는 범위는 이 넷 + "실시간 텔레그램 봇 상주"다. 동기화 UI 문제는 서버로 풀리지 않고 §3 Phase 2로 푼다.

---

## 3. 로드맵 (체크리스트)

**결정: 완전 재작성하지 않는다.** 2세대 본체는 작동하며 새로 짜면 같은 것을 다시 만든다. 1세대만 버리고, 2·2.5세대를 한 패키지로 합친 뒤, 순환을 배선한다.

### Phase 0 — 정리 (약 1주) · 선행 필수

- [ ] 0-1 1세대 처분: 루트 `.py` 20개 + `rename_threads.sh` + `agents/` + `scheduled/` + `skills-draft/` + `pdf_output/` 삭제(또는 `_archive/legacy_2026-04/`로 이동 — §5 미결). `apple_notes_raw/`는 볼트 `raw/applenotes`에 이미 606건 이관됐는지 확인 후 처분. 완료 판정: `grep -rn "/Users/lhg" --include='*.py' .` 0건.
- [ ] 0-2 살아 있는 3개(`claude_client`·`memory_manager`·`diff_learner`) 패키지 안으로 흡수. `sys.path.insert` 전부 제거.
- [ ] 0-3 `vault_pipeline`을 `orchestrator`에 통합(패키지명은 §5 미결, 임시 `orchestrator`). 공용 모듈 4개로 수렴: `vault_io`(frontmatter 파서 1벌·write_note·섹션 읽기쓰기), `ledger`(load/save 1벌, dry_run 지원), `telegram`(send·note_url 1벌), `config`(env 1곳, `DONE_STATES` 1벌, 경로 상수 1벌). 순환 import 0.
- [ ] 0-4 프롬프트 한 폴더로(`prompts/` 또는 `prompts.py` 1개). 문체 학습 프롬프트 4벌 → 1벌, 저장소는 Honcho `{channel}-corrections` + 볼트 기록 2곳으로.
- [ ] 0-5 장부·로그를 볼트 밖으로. 후보: 저장소 `state/`(git 추적, 볼트 아님) 또는 별도 브랜치 — §5 미결. 완료 판정: 볼트 커밋 중 장부만 바뀐 커밋 0.
- [ ] 0-6 CI 테스트: `requirements-dev.txt`에 pytest, `.github/workflows/test.yml`(PR·push마다). 현재 테스트 전부 통과 상태로.
- [ ] 0-7 yt_research 공유 계약을 데이터 파일 1개로: `data/contract.json`(카드 파일명 규칙·형식 라벨·카테고리 키워드·frontmatter 키 순서·브랜드 룰북·DG-ID 규칙). 파이썬은 import, yt_research는 GitHub raw로 읽기(`benchmarkRules.ts` 방식과 동일). `publish_at` 드리프트 해소.
- [ ] 0-8 저장소 루트 `.obsidian/` 제거(볼트는 `vault/`만). `raw/clipings` 오타 폴더 병합.
- [ ] 0-9 `docs/ARCHITECTURE_V2.md`·`CLAUDE.md` 코드 구조 표를 통합 후 구조로 갱신.

### Phase 1 — 지식 배선 (약 2~3주) · 불편 2·5·6의 해법

- [ ] 1-1 **브리프 단계 "내 지식 검색" 주입**. `handle_keyword_approved` 브리프 직전에 검색기 호출: 대상 = `제텔카스텐/3. 의견`·`4. 주장`·`5. 글감`(author 이한결, `_ai` 아님, candidate 아님 — 헌법 B-2), `6. 사례은행`(초록), `raw/스레드_아카이브/*.csv`(본인 글), `SNS…/03 라이브러리/38 주제별 콘텐츠`. 방식: 1차 키워드·태그 매칭, 2차 임베딩(yt_research `_system/yt-research/embedding-index.json` 재사용 검토). 상위 5~8건을 브리프에 `[내 지식 — 반드시 이 안에서 주장·사례를 고른다]` 블록으로 주입. 카드 frontmatter `참조원본: [[...]]` 필수 기록.
- [ ] 1-2 **근거 0건 게이트**: 검색 결과 0건이면 초안을 쓰지 않는다. 카드 `needs_human` + 텔레그램 "이 주제로 3분만 녹음해 주세요(플라우드) 또는 글감 붙여넣기" 요청. 사람 입력을 뒤쪽 수정에서 앞쪽 발화로 옮긴다.
- [ ] 1-3 **출처 게이트**: 초안 완성 후 LLM 1회로 "주장별 출처 표"(주장 → 참조원본 노트 / 리서치 링크 / 없음). '없음'이 1개라도 있으면 해당 문장을 일반 서술로 낮추거나 삭제한 2차안을 만들고, 카드에 표를 남긴다. 글 평가 50점표에 `source_coverage` 항목 추가.
- [ ] 1-4 **발제 전환**: `daily_intake`를 LLM 브레인스토밍에서 "제텔카스텐 3~4단계 중 `used_in` 없는 노트 + 최근 플라우드 의견" 기반으로. 발제 카드에 근거 노트 링크 포함. 대기 카드(`needs_human`)가 N개(기본 5) 이상이면 발제 중단.
- [ ] 1-5 **역방향 관문 완성**: `feedback.atomize` 산출을 `1. 메모` 직행 대신 `_system/candidates/`에 `status: candidate`로 격리(헌법 §4 관문 3). 텔레그램 승인(Phase 2 버튼, 그 전엔 답장 "승인 N")으로 정식 승격. 승격 시 원본 노트(`참조원본`)에 `used_in: [[카드]]` 역기록(헌법이 허용한 유일한 자동 수정). 기존 19건의 `원출처_추적: 필요` 메모를 첫 승인 대상으로.
- [ ] 1-6 **영상 발화 환류** — §4 상세 설계. 완료 판정은 §4-7.
- [ ] 1-7 **플라우드 triage 확장**: 교사 글감 외에 "학부모 SNS 씨앗" 갈래 추가 → 기준 충족 시 intake 카드 자동 생성(`## 📄 글감` 섹션에 발화 발췌, 근거 노트 링크). 현재 `.claude/skills/plaud-zettel`의 승격 로직을 코드로.
- [ ] 1-8 **문체 학습 실효화**: `script_learn`·`style_learn` 통합본이 실제로 lessons를 만드는지 검증(현재 `lessons: 0`). 학습 결과가 작가 프롬프트에 주입되는 경로를 테스트로 고정.

### Phase 2 — 승인 인터페이스 교체 (약 1주) · 불편 1·4의 해법

- [ ] 2-1 텔레그램 인라인 버튼(승인 / 수정 / 기각 / 예약)으로 카드·후보·원고 승인. 콜백 수신처: yt_research 웹훅(`app/api/telegram/webhook/route.ts`, 이미 상시 HTTP) 또는 새 봇 — §5 미결. 동작 = Contents API로 frontmatter 변경(승인) / `_system/feedback` 노트 생성(수정) / candidate 승격(지식).
- [ ] 2-2 알림 메시지에 버튼 부착: 초안 완성·발행 승인 요청·candidate 승인·영상 매칭 확인(§4-3).
- [ ] 2-3 옵시디언은 읽고 생각하는 도구로만. 승인 흐름에서 git 편집 제거. `docs/OBSIDIAN_SETUP.md` 갱신.
- [ ] 2-4 (선택) Obsidian Git 자동 pull 간격 재조정 — Phase 0-5로 소음이 사라진 뒤 판단.

### Phase 3 — 플라우드 입력 복구 (사용자 액션 + 소규모 코드)

- [ ] 3-1 **사용자**: 플라우드 앱 자동 전사 켜기. 대기 6건(9/3~9/7) 전사 → 다음 실행에 자동 처리되는지 확인.
- [ ] 3-2 미전사 N일 이상이면 텔레그램 리마인드(현재는 요약에만 표시).
- [ ] 3-3 `수집함/plaud/` 수동 투입 경로 라이브 테스트 1회.

### Phase 4 — 서버 (Phase 2 성공 후, MASTER_PLAN D-14 준수)

- [ ] 4-1 윈도우 노트북 → Ubuntu Desktop + Tailscale. 역할 3개 한정: ① 텔레그램 봇 상주(Phase 2에서 새 봇을 택했을 때) ② `claude -p` 야간 에이전트(Max 구독 토큰, `llm.py` 폴백 경로 이미 있음) ③ ffmpeg·Whisper 렌더링(쇼츠·§4 전사 폴백). 스케줄 본체는 GitHub Actions 유지.
- [ ] 4-2 뷰트랩 쿠키 동기화 launchd → 서버 cron 이전.
- [ ] 4-3 무인 24시간 사이클 1회 검증.

---

## 4. 영상 발화 환류 상세 설계 (Phase 1-6, 2026-09-19 사용자 추가 요청)

### 4-1. 목적
촬영본은 원고와 다르게 말해진다. 그 차이에는 두 가지 가치가 있다. ① 발화 쪽이 더 나은 대목은 다음 원고에 반영해야 한다(작가 학습·원고 업그레이드). ② 실제로 말한 문장은 사용자 본인의 확정된 생각이므로 제텔카스텐의 1급 재료다(구술 verbatim). 지금은 둘 다 버려진다.

### 4-2. 입력원과 전사 방법 (우선순위 순)

| 순위 | 입력 | 전사 | 비용·위치 |
|---|---|---|---|
| 1 | 로컬 쇼츠 편집 산출물 `artifacts/shorts/<원본>/<v>/subtitles.srt`·`final.mp4` | 이미 있음(mlx-whisper / faster-whisper) | 0. 로컬(맥·서버) |
| 2 | 유튜브 채널 업로드(롱폼·쇼츠) | 자막 API(`youtube-transcript-api`, 자동자막 포함) → 없으면 yt_research `/api/transcript`(InnerTube+Gemini ASR, `YT_RESEARCH_URL` 재사용 — `pool_enrich` 패턴) | GitHub Actions |
| 3 | 인스타그램 릴스(본인 계정) | Instagram Graph API `me/media?fields=media_url,permalink,caption,timestamp,media_type` → `media_url` mp4 다운로드 → faster-whisper(ko, CPU, 60초 릴스 OK) | Actions. Graph API 불가 시 로컬 폴백(4순위) |
| 4 | 로컬 mp4/URL 수동 투입 | `tools/video_transcribe.py`(`tools/shorts_edit.py` Whisper 코드 재사용) → `수집함/영상전사/`에 md 드롭 | 로컬(맥·서버) |

### 4-3. 원고 매칭 규칙
1. 원고 frontmatter에 `published_url`(또는 기존 `유튜브:` 필드)이 있으면 확정.
2. 없으면 제목·게시일·키워드·본문 유사도로 LLM이 후보 1~3개 제안 → 텔레그램 "이 영상 = 이 원고?" (Phase 2 버튼, 그 전엔 답장 `1`/`2`/`3`/`없음`). 확정되면 원고 frontmatter에 `published_url`·`video_id` 자동 기록(사람 작업 대체).
3. 원고가 없는 즉흥 영상도 전사·지식 저장은 한다(대조만 생략). — §5 미결 ③
4. 검색 범위: `05 리뷰/대기`·`05 리뷰/완료`·`06 제작/64 발행완료`·`파이프라인/활성`(format youtube·reels).

### 4-4. 대조·업그레이드 (LLM 1회, JSON 출력)
입력: 원고 본문, 발화 전사(타임스탬프 포함), 있으면 성과(조회수·좋아요·댓글 요약 — yt_research가 이미 수집).
출력:
- `차이`: 뺀 것 / 더한 것 / 순서 바꾼 것 / 표현 바꾼 것 (각 근거 문장 인용)
- `판단`: 대목별로 원고·발화 중 어느 쪽이 나은지 + 이유(후킹·논리·구어 리듬·정확성 기준)
- `개선안`: 발화의 장점을 반영해 **다음 촬영용으로 재작성한 원고** (구조·핵심 주장은 원고 유지, 문장은 발화 쪽 채택)
- `교훈`: 문체·구조 교훈 3~5줄(다음 원고 프롬프트용, "말할 때는 ~한다" 형식)
- `정확성_경고`: 발화에서 원고에 없는 수치·연구·단정이 나왔으면 목록(전문성 방어 — 다음 촬영 전 확인 대상)

기록:
- 원고 파일에 `## 🎤 발화 대조 — 날짜`, `## ✍️ 발화 반영 개선안 — 날짜` 섹션 추가. frontmatter 원문 보존·본문 길이 안전장치는 `script_feedback.apply_one` 것을 재사용.
- `SNS…/07 운영/62 셀프 피드백/영상 발화 학습.md`에 교훈 누적.
- Honcho `{channel}-corrections`에 교훈 저장(통합 문체 학습 루프와 같은 세션) → 작가·유튜브 원고 프롬프트에 자동 주입.
- `data/youtube_voice.md` 보이스 프로필에 "실제 발화 발췌" 갱신 후보를 제안(자동 반영은 하지 않고 사람 승인).

### 4-5. 제텔카스텐 저장
- **전사 원문(불변)**: `raw/영상전사/<채널>_<video_id>_<제목>.md`. frontmatter: `출처: youtube:<id>` 또는 `instagram:<shortcode>`, `published_url`, `recorded`(게시일), `duration`, `원고: [[원고 파일]]`(매칭 시), `author: 이한결(구술)`, `verbatim: true`. raw는 사람 소유 불변 영역이므로 자동화는 **추가 전용**(기존 파일 덮어쓰기 금지).
- **원자화**: 기존 플라우드 triage를 그대로 재사용한다. 전사를 `Recording(id="youtube:<id>", name=제목, recorded=게시일, transcript=전사, source="video")`로 감싸 `process_recording`에 넣으면 `1. 메모`(구술 verbatim)·`2. 키워드`(K_ai)·`3. 의견`·`6. 사례은행`(신호등)이 자동 생성된다. "영상 = 녹음"이라 헌법 규칙(author 이한결(구술), verbatim, 출처 필수)이 그대로 맞는다.
- triage에 **영상 모드**: 교사 글감 판정 끄기(학부모 콘텐츠), 대신 "학부모 SNS 재활용 씨앗"(스레드·뉴스레터 후보) 갈래 → Phase 1-7과 같은 intake 카드 생성 옵션.
- 생성 메모에 `used_in: [[원고]]`·`published_url` 기록 — "이 지식은 이미 이 영상에서 쓰였다"를 남겨 발제(1-4)가 중복 주제를 피하게.
- 장부: `video_feedback_ledger.json`(video_id 기준, Phase 0-5 위치 규칙 따름).

### 4-6. 구현 위치
- 모듈 `orchestrator/video_feedback.py`(Phase 0 통합 후 위치 조정): `list_new_videos()` / `fetch_transcript()` / `match_script()` / `compare_and_upgrade()` / `archive_transcript()` / `atomize()` / `run(--dry-run, --video-url, --since-days)`.
- 워크플로우 `.github/workflows/video-feedback.yml`: 매일 1회(KST 새벽, 다른 cron과 분산) + 수동(`video_url` 입력).
- 로컬 폴백 `tools/video_transcribe.py`: mp4/URL → srt·md → `수집함/영상전사/` 드롭(4-2의 4순위).
- 시크릿: `YOUTUBE_API_KEY`(또는 `YT_RESEARCH_URL`+`YT_RESEARCH_PASSWORD`), `IG_ACCESS_TOKEN`/`IG_USER_ID`(MASTER_PLAN Phase C 토큰과 공용), 기존 텔레그램·LLM.
- 테스트: 매칭 규칙·diff JSON 파싱·raw 추가전용·Recording 래핑·장부 dedupe(LLM·네트워크 mock).

### 4-7. 완료 판정
실제 발행 영상 1편(유튜브 1 + 인스타 1)으로 end-to-end 1회: 전사 → 텔레그램 매칭 확인 → 원고에 대조·개선안 섹션 → `raw/영상전사/` 1건 → `1. 메모` N건(`used_in` 포함) → Honcho 교훈 저장 확인.

### 4-8. 미결 (사용자 결정)
① 인스타 접근: Graph API(토큰 발급 필요) vs 로컬 폴백만. ② 개선안 저장: 원고 파일에 섹션 추가 vs 별도 파일(`원고_…_v2.md`). ③ 원고 없는 즉흥 영상도 지식 환류(기본 예). ④ 성과 지표(조회수·댓글) 결합 여부와 출처. ⑤ 쇼츠 편집 산출물의 srt를 1순위로 쓸지(편집 컷 반영본이라 원본 발화와 다를 수 있음).

---

## 5. 미결 사항 · 결정 레지스트리

### 미결 (사용자 확인 필요, 임의 결정 금지)
1. 1세대 처분: 삭제 vs `_archive/legacy_2026-04/` 이동(이력은 git에 남음).
2. 통합 패키지 이름: `orchestrator` 유지 vs `dreamgrow`(통합기획 v3의 `src/` 구조 채택 여부).
3. 장부·로그 위치: 저장소 `state/`(git 추적) vs 별도 브랜치 vs Actions cache.
4. 텔레그램 버튼 콜백 수신처: yt_research 웹훅 확장 vs 새 봇(서버 상주).
5. 리눅스 서버 도입 여부와 시점(Phase 2 이후 권장).
6. 발제 중단 임계값(대기 카드 N개, 기본 5).
7. §4-8 ①~⑤.
8. Phase 순서 확정(제안: 0 → 1-1·1-2·1-5 → 2 → 1-6 → 3 → 1 나머지 → 4).

### 결정 레지스트리 (사용자 확정분만)
| 날짜 | 결정 | 근거 |
|---|---|---|
| 2026-09-19 | 완전 재작성하지 않고 정리+배선으로 간다 (AI 제안, 사용자 이의 없음 — 확정 시 갱신) | §2-6 |

---

## 6. 진행 로그

- 2026-09-19 · Claude(Fable 5.1) · 전수 진단 완료(코드 3세대·중복·순환 실측·yt_research 연동·1세대 생사). 이 문서 작성, 브랜치 `claude/knowledge-cycle-roadmap-2026-09` 생성·푸시. **코드 변경 없음.** 사용자 추가 요청(영상 발화 환류)을 §4로 설계.
