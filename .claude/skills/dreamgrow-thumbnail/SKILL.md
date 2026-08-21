---
name: dreamgrow-thumbnail
description: 드림그로우 유튜브 썸네일을 대화 루프로 제작한다 — 참조 이미지(실제 책 표지 등) 확인 → 피부 리얼리즘 프롬프트로 장면 생성 → 확정 v2 스타일(검은고딕 중앙, =="강조"== 큰따옴표 노란색) 렌더 → 보여주고 피드백 받아 반복. "썸네일 만들어줘", "썸네일 수정", "썸네일 다시", "N행 썸네일", "표지 넣어서 썸네일", "썸네일 스킬" 같은 요청이면 반드시 이 스킬을 사용한다. 시트 자동 파이프라인(orchestrator/thumbnail.py)과 같은 엔진을 세션 안에서 손으로 돌리는 스킬이다.
---

# 드림그로우 썸네일 제작 루프

주제 하나의 썸네일을 **만들고 → 보여주고 → 고쳐서 → 다시 만드는** 반복 루프.
엔진은 `orchestrator/thumbnail.py`(시트 자동 파이프라인과 동일)를 그대로 쓴다 — 스타일·프롬프트를
여기서 새로 짓지 말 것. 코드 상수가 곧 확정 스펙이다.

## 시작하기 전에 반드시 확인할 3가지 (매 루프마다)

### ① 참조 이미지 — 파일명을 사용자에게 물어본다

실제 책 표지 등 참조 이미지는 `data/thumbnail_assets/`에 있다
(GitHub: https://github.com/dream0grow/dream-grow-content-automation/tree/main/data/thumbnail_assets).

1. `ls data/thumbnail_assets/` (하위 폴더 포함)로 지금 있는 파일 목록을 뽑아 사용자에게 보여준다.
2. **"이번 썸네일에 쓸 참조 이미지 파일명이 무엇인가요?"라고 반드시 물어본다**
   (AskUserQuestion 사용 — 목록의 파일들을 선택지로, "참조 없이 생성"도 선택지로).
3. 원하는 파일이 아직 없다면: 위 GitHub 경로에 Add file → Upload files로 올려달라고 안내하고,
   올라오면 `git pull` 후 진행한다.
4. 주의: 맥에서 올린 한글 파일명은 NFD로 저장된다 — 파일 탐색은 `thumbnail.find_assets(키워드)`를
   쓰면 NFC 정규화까지 처리된다. 직접 glob하지 말 것.

### ② 피부·얼굴 리얼리즘 프롬프트 — 예외 없이 항상 적용

사람이 나오는 생성 이미지는 AI 티가 나면 실패다. 아래 블록(코드의 `thumbnail.REALISM` 상수와
동일)을 **photo_prompt 끝에 항상** 덧붙인다. 코드 경로(`run_one`/`run_sheet` 확정 렌더)는 자동으로
붙이지만, 이 스킬에서 프롬프트를 손으로 조립할 때도 빠뜨리지 않는다:

> visible pores, skin texture, fine wrinkles, slight skin imperfections, vellus hair, peach fuzz,
> natural skin blemishes, slight freckles, no makeup, candid shot, snapshot, unfiltered,
> amateur photography, natural daylight, soft ambient light, shot on 35mm lens, iPhone photo

(뜻: 보이는 모공·피부 결, 미세 주름·잡티, 잔털, 연한 주근깨, 민낯, 연출 없는 스냅샷,
무보정 아마추어 사진, 자연광, 35mm/아이폰 질감)

### ③ 벤치마킹 이미지 — 있으면 달라고 요청한다

구도·분위기를 따라갈 벤치마킹 썸네일이 있는지 **사용자에게 물어본다**. 있다면:
- 채팅 첨부는 파일로 저장되지 않으므로, `data/thumbnail_assets/`에 올려달라고 하거나
  유튜브 URL을 받아 `thumbnail.ocr_benchmark(url)`로 문구·그림 묘사를 뽑는다.
- 벤치마킹 이미지는 "이 구도·감정을 따라 하라"는 지시로 photo_prompt에 반영한다
  (참조 표지 이미지와 함께 `image_gen.edit_with_refs`의 참조로 넣어도 된다).

## 제작 절차

1. **입력 수집**: 키워드(주제), 확정 문구(썸네일에 얹을 글자), 영상 제목, 이미지 지시.
   시트에서 가져올 때는 S열(만든 제목)을 `thumbnail.parse_made_title()`로 나눈다 —
   괄호 안은 유튜브 제목이므로 **썸네일에 넣지 않는다**.
2. **문구 강조**: 핵심 단어 1개(최대 2개)를 큰따옴표에 넣어 `=="단어"==` 형태로 감싼다
   (렌더에서 큰따옴표까지 노란색 #ffd400). 예: `=="고전"==을 만화책처럼`.
3. **배경 생성**: 참조 이미지가 있으면
   `image_gen.edit_with_refs(프롬프트+REALISM, 참조경로들, 캐시디렉토리)` —
   프롬프트에 "reference image의 책 표지를 그대로 재현(재디자인 금지)"을 명시.
   참조가 없으면 photo_prompt(+REALISM)로 일반 생성. 생성 키(OPENAI/GOOGLE)가 세션에 없으면
   그라데이션 폴백으로 시안만 만들고, 최종본은 GitHub Actions(thumbnail 워크플로우)로 돌리라고 안내.
4. **렌더**: 확정 v2 스타일이 기본이다 —
   ```python
   from orchestrator import thumbnail
   thumbnail.ensure_fonts(); thumbnail.ensure_dohyeon(); thumbnail.ensure_blackhansans()
   spec = {"style": "v2", "line1": '=="고전"==을 만화책처럼', "line2": "읽는 방법",
           "copy": "...", "photo_prompt": "... , " + thumbnail.REALISM,
           "_bg_file": 생성된_배경_경로_또는_생략}
   thumbnail.render([spec], 출력폴더, prefix="이름")
   ```
   스타일 스펙(코드 상수가 진실): 검은고딕(Black Han Sans) 중앙 정렬 하단 2줄
   `V2_LINE_PX`(12자 초과 시 `V2_LINE_PX_SMALL`), 검은 외곽선, 본문 흰색 + `==...==`만 노란색.
   도현체 좌측 스타일이 필요하면 `style` 생략(v1) — 킥커 "현직 초등 교사가 알려주는" 포함.
5. **보여주기**: PNG를 사용자에게 전송(SendUserFile 등)하고 피드백을 받는다.
6. **반복**: 피드백을 반영해 **①~③ 확인부터 다시** 루프를 돈다 — 참조 이미지 교체,
   문구·강조 수정, 배경 재생성, 스타일 전환 등. 사용자가 확정할 때까지 반복한다.

## 확정본 처리

사용자가 "이걸로 확정"하면:
- 볼트 저장: `thumbnail.save_render_to_vault(키워드, png, jpg)` → `vault/파이프라인/썸네일/`
  (JPG가 유튜브 업로드용). 커밋·푸시까지.
- 시트 행 기반 작업이었다면 R열(만든 썸네일)에 `=IMAGE("raw URL")`, Q·S를 파랑(`DONE_BLUE`)으로 —
  자동 파이프라인과 같은 규약 (노랑 = 사람 컨펌, 파랑 = 작업 완료).
- 텔레그램 전송이 가능하면 `telegram_notify.send_photo()`로도 보낸다.

## 알아둘 것

- 이 스킬은 자동 파이프라인(`thumbnail.yml` 2시간 cron / Run workflow)의 **수동·대화형 짝**이다.
  시트에 여러 행을 일괄 처리할 때는 스킬 대신 워크플로우를 쓰라고 안내한다.
- 스타일·크기를 바꿔달라는 요청이 "앞으로 계속" 성격이면 `orchestrator/thumbnail.py`의 상수를
  고치고 커밋해 파이프라인과 스킬이 같이 바뀌게 한다. 일회성이면 spec만 조정한다.
- 드림그로우 절대규칙(불안 조장·비난·효과 단정 금지)과 "가린 정보는 본편이 갚는다"는
  문구에도 그대로 적용된다.
