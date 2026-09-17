# 쇼츠 자막 스타일 프리셋

`tools/shorts_edit.py --style <이름>`이 읽는 자막 스타일. 파일 하나가 프리셋 하나다.
기본값은 `growcircle`(그로우써클 유튜브). 새 채널·새 무드가 생기면 JSON을 복사해 이름만 바꾸면 된다.

| 키 | 뜻 | 비고 |
|---|---|---|
| `font` / `font_fallbacks` | 서체와 대체 서체 순서 | 설치 안 돼 있으면 fallbacks 중 설치된 첫 폰트. `data/fonts/`에 otf/ttf를 넣으면 설치 없이 사용 |
| `size` | 자막 크기(px) | 1080×1920 화면 기준 절대값 |
| `color` / `outline_color` / `outline` | 글자색 / 테두리색 / 테두리 두께 | `#RRGGBB` |
| `highlight_color` | `==단어==` 강조색 | 썸네일 스킬의 `=="강조"==` 관례와 동일 |
| `box`, `box_color`, `box_alpha` | 글자 뒤 반투명 상자 | `box: true`면 테두리 대신 상자 |
| `align` / `margin_v` | 위치(`top`/`center`/`bottom`) / 가장자리에서 띄우는 px | 쇼츠는 하단 UI(제목·버튼)를 피해 `bottom` + 500px 안팎 권장 |
| `max_chars` / `max_lines` | 한 줄 글자 수 / 한 장 줄 수 | Whisper 문장을 이 기준으로 짧게 끊는다 |
| `hook` | 상단 후킹 자막(`--hook "문구"`) 전용 덮어쓰기 | 없는 키는 본문 자막 값을 물려받는다 |

## 참조 영상에서 스타일 뽑는 법

1. 참조 쇼츠를 정지시켜 자막이 보이는 장면을 캡처한다(폰 스크린샷이면 충분).
2. 캡처를 Claude Code 세션에 올리고 "이 자막 스타일로 growcircle 프리셋 맞춰줘"라고 하면
   서체 계열·색·테두리·위치를 읽어 JSON을 고친다.
3. `python3 tools/shorts_edit.py <영상> --mode burn --style growcircle`로 다시 구워 비교한다
   (재분석·재렌더 없이 자막만 다시 굽는다).

`growcircle.json`의 현재 값은 한국 토킹헤드 쇼츠의 전형(흰 볼드 + 검은 테두리 + 노란 강조,
하단 1/4 지점 큰 자막)으로 잡은 출발점이다. 참조 영상 캡처로 대조한 뒤 확정한다.
