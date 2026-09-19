# 풀링 영상 만들기 탭 — 조회수·구독자 열과 벤치마크 후보 자동화 (2026-09-19)

시트: `Y_📚자기 주도 학습` › `풀링 영상 만들기` (gid 787785781)

## 열 개편

A(날짜 및 키워드)와 영상 URL 사이에 두 열을 넣었다. 나머지 열은 두 칸씩 오른쪽으로 밀렸다
(예전 L 내가 만들 영상 키워드 → N, S 만든 제목 → U, X 만든 도입부 → Z).

| 열 | 헤더 | 내용 |
|---|---|---|
| B | 조회수 (게시일) | `441.1만회` ⏎ `게시 2019-08-09` ⏎ `검색일 기준 2,597일 · 일평균 1,698회` (경과일은 A열 검색일 기준) |
| C | 구독자 수 | `37.1만명` ⏎ `조회/구독 11.9배` |

값은 YouTube Data API 기준 갱신 시점 값이다(검색 당시 값이 아님). 헤더 셀 메모에 같은 설명이 있다.

**코드는 열 문자를 박지 않고 헤더 이름으로 위치를 잡는다** (`orchestrator/pool_cells.resolve_pool_columns`,
`thumbnail.resolve_columns`, `youtube_body.resolve_columns`). 열을 또 옮겨도 헤더 이름만 유지하면 된다.
`thumbnail.LAST_COL` 은 `AZ` 로 넓혔다 — 예전 `S` 는 열 삽입 뒤 '만든 썸네일/만든 제목'이 읽기 범위 밖으로 밀려
폴백 인덱스로 엉뚱한 열에 쓰는 사고를 냈다(2026-09-19 14:06 크론, 68행·12행 손으로 복구).

## 자동화

| 모듈 | 하는 일 | 실행 |
|---|---|---|
| `orchestrator/viewtrap_keywords.py` | 5점 키워드의 영상을 풀링 탭에 추가할 때 B/C를 뷰트랩 응답(viewCount·subscriberCount·publishedAt)으로 바로 채움. 조회수 top5 + 교육·육아 채널 + **벤치 후보** 세 묶음 | 매일 09:00 KST |
| `orchestrator/pool_enrich.py` | B/C가 빈 행을 YouTube API(또는 yt_research 사이트 `/api/videos-refresh`)로 채우고, 노란색이 아닌 행을 채점해 후보(≥7점)의 C셀을 연두색으로 칠하고 메모에 사유를 남김 | 6시간마다 (`pool-enrich.yml`) |
| `orchestrator/benchmark.py` | 규칙(`data/benchmark_rules.json`) + Claude 판정(`data/benchmark_examples.json`의 노란 행 예시 few-shot) | 위 둘이 호출 |

색 약속: **노랑 = 사람이 확정한 벤치마크(D열 URL 셀)**, 연두 = 자동 후보(C열), 파랑 = 렌더 완료(썸네일 파이프라인).
자동화는 노란 행을 절대 건드리지 않고 예시로만 쓴다. 후보를 확정하려면 D셀을 노랗게 칠하면 된다.

필요한 GitHub Secrets (새로 추가): `YOUTUBE_API_KEY` **또는** `YT_RESEARCH_URL`(예 `https://yt-research-two.vercel.app`)
+ `YT_RESEARCH_PASSWORD`(사이트에 APP_PASSWORD 가 걸려 있을 때). 기존 `GSHEET_SA_JSON`, `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` 재사용.

로컬/샌드박스 실행: google-auth 를 못 쓰는 환경이면 `GSHEET_ACCESS_TOKEN`(1시간짜리 토큰)을 넣으면 된다.

```
python3 -m orchestrator.pool_enrich --dry-run --no-llm      # 규칙 점수만 미리보기
python3 -m orchestrator.pool_enrich --rescore                # 전체 다시 채점
python3 -m orchestrator.pool_enrich --refresh-examples       # 시트 노란 행 → benchmark_examples.json
```

## 벤치마크 판정 기준 (사용자 기준을 그대로 옮김)

1. 유명인(오은영·강형욱·미미미누·최민준·조선미…)이 나오면 제외 — 사람 때문에 보는 조회수.
2. 구독자 많은 채널·방송사 클립·뉴스·키즈 채널 제외 — 구독자 대비 조회수(배율)가 높은 소규모 채널 우선.
3. 썸네일·제목만으로 조회수를 얻은 것 같은 영상 — 학부모 정보성이 아니어도 제목 구조가 베낄 만하면 통과.

2026-09-19 시트 분석(노란 39행 vs 그 외 146행, 자동 추가된 21~205행 기준):

- 노란 행 중앙값: 조회 37만 · 구독 40만 · 15분. 교육·육아 묶음의 노란 행은 조회 24만 · 구독 32만(21/26이 구독 60만 이하).
- 그 외 행 중앙값: 조회 318만 · 구독 135만 — 키즈·음악·방송 클립이 조회수 상위를 다 차지한다.
- 노란 행의 채널: 어디든학교·교육대기자TV·교집합 스튜디오·꽁교육+·가든패밀리·데일리어썸·골라듄공부·육아메이트 미오·
  육아는아빠가·소린TV·EBSi 등 10만~60만 규모 교육 채널 + 제목 구조 벤치(당구 실수 유형, 도어락 후회, 영단어 500개 듣기,
  형제 혼나는 유형).
- 같은 채널(교육대기자TV)도 조선미 편은 제외, 송재환·최치현·김붕년 편은 확정 → "인물"이 기준이지 채널이 아니다.
- 규칙만으로는 정밀도 ~50%(광고·음악·브이로그·퀴즈 채널이 샘) → Claude 판정에 노란/비노란 예시를 넣어 보완.

## yt_research 와의 연계

- 통계는 yt_research 사이트의 `/api/videos-refresh`(서버 YouTube 키, 50개당 쿼터 1+1)를 그대로 쓸 수 있다
  (`YT_RESEARCH_URL`). 사이트 검색 화면에서 같은 규칙으로 "벤치 후보" 배지를 보여주는 것은 yt_research 쪽
  `lib/benchmarkRules.ts` 가 이 리포의 `data/benchmark_rules.json` 을 읽어 처리한다.
- 댓글(AF~AJ)·영상요약(U→W)·도입부는 yt_research 의 `/api/comments`, `/api/transcript` 로 받을 수 있다 — 다음 단계.
