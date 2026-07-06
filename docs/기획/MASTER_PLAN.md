# MASTER_PLAN.md — 드림그로우 에이전트 OS 구축 마스터플랜
<!-- 이 문서는 Claude Code용 단일 진실원천(SSOT)이다.
     사람용 배경 설명은 가이드 1~4탄(docs/guides/)에 있으며, 충돌 시 이 문서가 우선한다.
     레포 위치 권장: docs/MASTER_PLAN.md. CLAUDE.md에 "구축 작업 시 이 문서 필독" 한 줄 추가할 것. -->

## 0. 이 문서 사용법 (AI 필독)
- 구축 관련 세션 시작 시 이 문서 전체를 읽는다.
- 작업은 반드시 §4 백로그의 Task ID 단위로 수행하고, 완료 시 체크 표시 + 완료일 기록.
- 이 문서에 없는 설계 판단이 필요하면 임의 결정하지 말고 사용자에게 질문한다.
- §2 폐기된 결정을 절대 부활시키지 않는다.

## 1. 시스템 개요

**목표**: 스레드 1편 → 뉴스레터·카드뉴스·릴스·유튜브 스크립트 자동 생성, 모바일 음성 승인 후 스레드·인스타 자동 발행, 실행할수록 학습하는 시스템.

**하루 사이클**:
```
23:30 collector: Raindrop→옵시디언 수집함 변환
04:00 team-content: 초안 생성 → 05 리뷰/대기/          [기존]
06:30 morning_briefing: 텔레그램으로 초안+버튼 푸시      [신규]
출근길 사용자: 텔레그램 음성/버튼 또는 옵시디언 받아쓰기로 지시
07:30 revision_loop: 음성지시 수집→초안 수정→재푸시→확정 처리 [신규]
매시  scheduled_publisher(Threads,기존) + instagram_publisher(신규)
21:00 diff-learn: 최종본 vs AI초안 diff → Honcho 학습    [기존]
금 저녁 주간회고(Fable): 규칙·스킬·corrections 재정비    [신규]
일 08:00 weekly_cleanup: 코드 건강검진                   [신규]
```

**인프라**: 개발=맥북 / 24시간 운영=옛 노트북(Ubuntu Desktop, 뚜껑닫힘 무시 설정) / 원격=Tailscale+SSH+tmux / 코드 동기화=Git(GitHub) / 볼트 동기화=Obsidian Sync 공식(서버에 Obsidian 앱 상시 실행) / **같은 폴더에 이중 동기화 금지**.

## 2. 확정 결정 레지스트리 (충돌 시 여기가 기준)

| ID | 결정 | 폐기된 이전안 |
|----|------|--------------|
| D-01 | 서버 OS = **Ubuntu Desktop** (Server 아님) | Ubuntu Server |
| D-02 | 알림·승인 채널 = **텔레그램 봇** (브리핑+음성수신+인라인버튼 통합) | 디스코드 웹훅 (2탄) |
| D-03 | 음성 입력 = 주력 **텔레그램 보이스**(faster-whisper 전사) + 예비 **옵시디언 00 인박스/음성지시.md**(iOS 받아쓰기) + 보조 **Plaud**(회의·강연 녹음 소재화) | Plaud 단독 (3탄 초기안) |
| D-04 | 문체 학습 = **기존 Honcho 체계 보존·확장** (diff_learner.py, {채널}-style/-corrections/-original-voice, brand-identity). 음성 수정지시 원문도 corrections에 저장 | style_guide.md 신규 구축을 심장으로 삼는 안 (1탄) |
| D-05 | 승인 워크플로우 = **기존 프론트매터 상태 기계** (리뷰대기→리뷰완료→발행완료) + 발행시간 필드. 새 상태 시스템 만들지 않음 | — |
| D-06 | 발행 = Threads(기존 scheduled_publisher 유지) + **Instagram Graph API 신규**(카드뉴스 캐러셀, 이미지는 GitHub Pages 공개 URL) | Manus 브라우저 자동화, 비공식 자동화 (계정 리스크로 금지) |
| D-07 | 수집 = **Raindrop 단일 깔때기** → collector가 옵시디언 00 인박스/수집함/으로 변환. 스레드·유튜브·Lilys·Viewtrap 모두 공유→Raindrop 경유. 유튜브 재생목록 방식은 선택지(전용 재생목록 필요, WL은 API 불가) | Obsidian Web Clipper 도입 |
| D-08 | 모델 정책: 주간회고·diff분석·skill-updater = **fable** / 창작 초안 = fable(사용량 부담 시 평일 opus·주말 fable 절충) / 야간 오케스트레이터 = opus / 리서치·검수 = sonnet / 렌더링·유틸 = haiku 또는 순수 파이썬 | 전 작업 단일 모델 |
| D-09 | 에이전트 수 = 4~5명 유지 (researcher/writer/reviewer/designer + 청소반장). 채널별 분화 금지 | 채널별 에이전트 증설 |
| D-10 | 원본 연결 의무: 초안 생성 전 01-아이디어-수집·03 라이브러리에서 관련 원본 2~3편 + 수집함 미검토 노트 확인, frontmatter에 `참조원본`/`참조수집` 기록, 문장 복사 금지(재창조) | — |
| D-11 | Plaud 연결: 대화형 = MCP(`npx -y @plaud-ai/mcp@latest install`, 서버는 `--no-login` + `ssh -L 8199` 인증), 크론 자동화 = **CLI**(`plaud today`, `plaud transcript <id> -o`) | MCP 단독 |
| D-12 | 볼트에 Git 붙이지 않음. 볼트=Obsidian Sync, 코드 레포=Git. 첨부파일 많은 폴더 Git 커밋 금지 | — |
| D-13 | 힉스필드 영상화·Manus 홈페이지·헤르메스 설치 = **구축 범위 외** (운영 안정화 후 순차: 3~4주차) | 3일 내 포함 |
| D-14 | 이전 순서: 음성 루프 실전 투입이 서버 이전보다 우선. 이전 지연 시 맥북이 임시 서버 (launchd 유지) | 3일 내 이전 강행 |

## 3. 안전 규칙 (모든 자동화에 적용, 완화 금지)

1. **명시적 확정 원칙**: "확정/발행해/올려" 명시 표현이 있는 초안만 발행 대기열 진입. 모호한 표현("괜찮네")은 발행 사유 아님 → 되묻기만 한다.
2. **채널별 개별 확정**: "전부 확정" 명시가 없는 한 채널마다 따로 확정 받는다.
3. **회수 유예**: 확정 즉시 발행 금지. 발행시간(기본 당일 19:00)까지 상태 되돌림으로 취소 가능해야 한다.
4. 검수→재작성 루프 상한 **2회**. 초과 시 사람에게 판단 요청.
5. 자동 청소는 파일 이동·lessons 요약까지만. 구조 변경은 제안만 하고 사람 결재.
6. 비밀값(.env: 텔레그램 토큰, THREADS/IG 토큰, RAINDROP_TOKEN, HONCHO 키)은 절대 커밋 금지.
7. 인스타 발행 첫 2주는 --dry-run 병행 후 완전 자동 전환.
8. 콘텐츠 필수 규칙(이모지 금지, 가짜 통계 금지, 'A가 아니라 B' 구조, 교실 에피소드, 마무리 서명) 유지 — 기존 CLAUDE.md 준수.

## 4. 작업 백로그

### Phase A — 기반 정비 (선행 필수)
- [ ] A-1 경로 하드코딩 제거: 전 스크립트의 `/Users/lhg/...` 절대경로를 config.py+.env로 통합. 완료판정: `grep -rn "/Users/lhg" content-automation/` 결과 0건 (2h)
- [ ] A-2 CLAUDE.md에 D-08 모델 정책 표 + "구축 세션은 docs/MASTER_PLAN.md 필독" 추가 (0.5h)
- [ ] A-3 rules/10-content-generation.md에 D-10 원본 연결 규칙 추가 (0.5h)
- [ ] A-4 diff_learner.py 모델을 .env `DIFF_MODEL`로 외부화 (기본 claude-fable-5) (0.5h)

### Phase B — 음성 승인 루프 (핵심 신공사)
- [ ] B-1 텔레그램 봇 생성(@BotFather) + 토큰 .env 저장 (0.2h)
- [ ] B-2 telegram_gateway.py: ①브리핑 발송(초안 요약+[확정][수정대기][보류] 인라인버튼) ②보이스 수신→ogg 다운로드→전사 큐 ③버튼 콜백→frontmatter 상태 변경. 의존: A-1 (3h)
- [ ] B-3 faster-whisper 설치 + 한국어 전사 함수 (대안: OpenAI Whisper API) (1h)
- [ ] B-4 Plaud MCP+CLI 설치·로그인 (맥북), 서버는 E-2 이후 --no-login+포트포워딩 (0.5h)
- [ ] B-5 revision_loop.sh: plaud today 전사 수집 + 텔레그램 보이스 전사 + 옵시디언 음성지시.md 취합 → claude -p로 초안 수정 → 지시 원문 Honcho corrections 저장 → 수정본 재푸시 → §3 규칙대로 확정 처리. 의존: B-2,B-3 (2.5h)
- [ ] B-6 morning_briefing.sh (06:30) + revision_loop(07:30) 스케줄 등록 (0.5h)
- [ ] B-7 통합 리허설: 실제 음성 지시→수정→확정→Threads 발행 완주 + 모호 지시 안전밸브 테스트 (1.5h)

### Phase C — 인스타그램 발행
- [ ] C-1 IG 프로페셔널 계정+FB페이지 연결, 기존 Meta 앱에 instagram_content_publish 권한 토큰 발급 (1h)
- [ ] C-2 자산 레포 dream-grow-assets 생성 + GitHub Pages 활성화 (PNG 공개 URL용) (0.5h)
- [ ] C-3 instagram_publisher.py: threads_publisher.py 미러 구조. 채널:인스타 + 발행시간 도달 감지 → PNG push → 캐러셀 컨테이너 생성 → 발행 → 상태 갱신·이동. --dry-run 필수 구현. 의존: C-1,C-2 (2.5h)
- [ ] C-4 scheduled 크론 슬롯에 통합 (0.5h)

### Phase D — 수집 일원화
- [ ] D-1 Raindrop 토큰 발급 → .env (0.2h)
- [ ] D-2 raindrop_sync.py: lastUpdate 기준 신규 조회 → 유형별 본문 추출(웹=페이지, 유튜브=youtube-transcript-api 자막, Lilys=요약페이지 텍스트) → sonnet 요약·카테고리 판정·활용각도 제안 → 00 인박스/수집함/노트 생성(frontmatter: 출처URL·수집일·카테고리·상태:미검토) (2h)
- [ ] D-3 23:30 크론 등록 + 금요일 주간 다이제스트 텔레그램 발송 (0.5h)
- [ ] D-4 (선택) 유튜브 전용 재생목록 "드림그로우수집" + Data API 연동 (1h)
- [ ] D-5 주간회고 점검 항목에 수집 활용률·3주 미검토 아카이브 추가 (0.2h)

### Phase E — 서버 이전 (B-7 성공 후 착수, D-14 준수)
- [ ] E-1 Ubuntu Desktop 설치(Try 모드 선검증) + lid switch ignore + Tailscale + Node 20 + Claude Code + Obsidian 앱 설치·Sync 로그인·자동시작 (2h)
- [ ] E-2 git clone + .env 이식 + Plaud --no-login 인증 + faster-whisper 재설치 (1h)
- [ ] E-3 launchd 6개 작업 → cron 변환 (install-schedules.sh 기반) + 신규 작업 포함 전체 스케줄표 확정 (1h)
- [ ] E-4 서버 단독 24시간 무인 사이클 1회 검증 후 맥북 launchd 비활성화 (0.5h+대기)

### Phase F — 자기개선 운영 루프
- [ ] F-1 scripts/code_health_rubric.md (10항목 100점) + weekly_cleanup.sh + 일 08:00 크론 (1.5h)
- [ ] F-2 금요일 주간회고 절차를 스킬로 등록 (Fable 세션: corrections 패턴→규칙 승격 검토, 수집 활용률, 모델 사용량 점검) (1h)
- [ ] F-3 memory/about_me.md 생성 (사용자 선호·브랜드 방향 축적) + 에이전트 필독 목록에 추가 (0.5h)

### 권장 순서
Day1: A 전체 + B-1~B-4 / Day2: B-5~B-7 + C-1~C-2 / Day3: C-3~C-4 + D-1~D-3 (+여유 시 E) / 이후: E → F → 3주차 힉스필드, 4주차 Manus·헤르메스 검토(D-13)

## 5. 보존 자산 (수정 시 하위호환 유지 의무)
diff_learner.py / memory_manager.py(Honcho) / scheduled_publisher.py / threads_publisher.py / zettel_reader.py / 스킬 5종 / team_runner.py / 프론트매터 상태 기계 / SNS-시스템 폴더 구조(01 수집·03 라이브러리·05 리뷰·06 제작) / 콘텐츠 필수 규칙 / 프로젝트 소유 경계(youtube/=10x인생 영역 수정 금지)

## 6. 미결 사항 (임의 결정 금지, 사용자 확인 필요)
- 창작 초안 모델: fable 상시 vs 평일 opus 절충 → 1주 사용량 관측 후 사용자 결정
- 발행 기본 시각 19:00 확정 여부, 채널별 차등 여부
- 텔레그램 전사: faster-whisper(로컬) vs Whisper API(유료) 최종 선택
- 유튜브 수집: 공유→Raindrop 단일화 vs 전용 재생목록 병행(D-4)
