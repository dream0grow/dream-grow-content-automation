---
name: dreamgrow-shorts-editor
description: DJI 오즈모 나노 등으로 촬영한 영상을 그로우써클(드림그로우) 유튜브 초벌 쇼츠(9:16 MP4)로 자동 편집한다 — 무음 컷(앞뒤 여유) + 박수=NG 컷 + Whisper 자막 + 스타일 프리셋(ASS) 자막 굽기(==강조== 노란색, 상단 후킹 자막) + 1080x1920 변환. "쇼츠 편집해줘", "오즈모 영상 편집", "촬영본 쇼츠로", "무음 잘라서 쇼츠", "SD카드 영상 편집", "DJI_… 이 영상으로 진행해줘", "이 쇼츠 자막 스타일로" 같은 요청이면 반드시 이 스킬을 사용한다. 엔진은 tools/shorts_edit.py — 색 보정은 하지 않고 원본 화질을 유지한다. 원본이 사용자 컴퓨터(구글 드라이브 동기화 폴더 등)에 있으므로 로컬 Claude Code/Cowork에서 돌려야 하며, 클라우드 세션에서는 영상에 손이 닿지 않는다.
---

# 드림그로우 쇼츠 편집 루프 (그로우써클 유튜브)

촬영 원본(오즈모 나노 MP4 등)을 **분석 → 컷 계획 확인 → 렌더 → 자막 → 스타일 굽기 → 피드백 반영**으로
초벌 쇼츠까지 만드는 반복 루프. 엔진은 `tools/shorts_edit.py` 하나다 — 편집 규칙을 여기서
새로 짓지 말 것. 코드 기본값과 `data/shorts_styles/*.json`이 곧 확정 스펙이다.

편집 규칙(video-lecture-editor와 동일 철학):
- 무음 구간 제거, 잘라낸 자리 앞뒤 `--pad`(기본 0.3초) 여유는 남긴다.
- **박수 소리 = 재촬영(NG) 표시** → 박수 직전 테이크를 잘라낸다.
- 색 보정 없음 — 원본 화질 그대로. 9:16(1080×1920) 변환과 자막만.

자막 규칙:
- 스타일은 프리셋(`--style`, 기본 `growcircle`)이 정한다: 서체·색·테두리·위치·한 줄 글자 수.
- Whisper 문장은 프리셋 `max_chars` 기준으로 짧게 끊어 쇼츠식 큰 자막으로 굽는다.
- `==단어==`는 강조색(노란색). 썸네일 스킬의 `=="강조"==` 관례와 같다.
- `--hook "첫 줄|둘째 줄"`은 상단 후킹 자막(제목). `--hook-seconds N`으로 앞부분만 노출.

## 0. 어디서 돌리나 (먼저 판단)

원본은 **사용자 컴퓨터**에 있다. 촬영본 폴더(구글 드라이브 데스크톱 동기화):
`~/Library/CloudStorage/GoogleDrive-leehg0211@gmail.com/내 드라이브/DJI_오즈모 영상`
(같은 이름의 `.LRF`(저해상 프록시)·`.WAV`가 함께 있다 — 엔진이 자동으로 `.MP4`만 고른다.)

- **로컬 Claude Code / Cowork(맥북)**: 이 스킬대로 바로 실행.
- **클라우드 세션(claude.ai/code 웹)**: 드라이브·유튜브 접근이 막혀 영상을 못 만진다.
  이때는 엔진·프리셋만 손보고, 사용자에게 **로컬에서 실행할 명령 한 줄**을 건넨다.

사전 확인(첫 실행 시 1회):
```bash
ffmpeg -version || python3 -c "import imageio_ffmpeg" || echo "설치: brew install ffmpeg (또는 pip install imageio-ffmpeg)"
python3 -c "import faster_whisper" 2>/dev/null || echo "자막용: pip install faster-whisper"
```
ffmpeg가 없으면 편집 자체가 불가 — 안내 후 중단. faster-whisper가 없으면 자막만 생략(편집은 진행).

## 1. 영상 지정

파일 경로, 폴더, 또는 **확장자 없는 이름**(`DJI_20260914072454_0008_D`)으로 받는다.
이름만 왔으면 `--source-dir "<촬영본 폴더>"`(또는 환경변수 `DG_OSMO_DIR`)를 붙인다.

```bash
export DG_OSMO_DIR="$HOME/Library/CloudStorage/GoogleDrive-leehg0211@gmail.com/내 드라이브/DJI_오즈모 영상"
python3 tools/shorts_edit.py DJI_20260914072454_0008_D --mode analyze
```

## 2. 분석 → 컷 계획을 반드시 먼저 보여준다

출력되는 세그먼트 목록·박수(NG) 감지 결과·최종 길이를 사용자에게 보여주고 확인받는다.
- 박수 오탐이 있으면 `--no-clap` 또는 `edit_plan.json`에서 해당 컷만 되돌리기.
- 컷이 너무 잘게/성기게 나오면 `--min-silence`(기본 0.9초)·`--pad`(기본 0.3초) 조정 후 재분석.
- 강의 스타일(여유 있게)을 원하면 `--pad 0.5`.
- 편집 후 180초 초과면 여러 편 분할을 제안한다.

## 3. 렌더 — 환경에 맞는 방식으로

**로컬 터미널(제한 없음)**: 한 번에 전부.
```bash
python3 tools/shorts_edit.py DJI_20260914072454_0008_D --hook "현직 초등교사가 알려주는|==후킹 문구=="
```

**Cowork 45초 bash 제한 환경**: 조각 렌더링 — 세그먼트 하나씩, 단계별로.
```bash
python3 tools/shorts_edit.py <영상> --mode render --segment 0   # 세그먼트별 반복
python3 tools/shorts_edit.py <영상> --mode concat
python3 tools/shorts_edit.py <영상> --mode subs                 # Whisper (수십 초 걸릴 수 있음)
python3 tools/shorts_edit.py <영상> --mode burn --hook "…"
```
세그먼트 하나가 45초를 넘길 만큼 길면 `run_in_background`로 실행한다.

가로 촬영본인데 인물이 중앙에 없으면 `--fit blur`(블러 배경 레터박스)를 제안한다.

## 4. 결과 확인 → 피드백 루프

`<영상명>_shorts/` 안: `final.mp4`(자막 포함) / `cut.mp4`(자막 전) / `subtitles.srt` /
`subtitles.ass` / `edit_plan.json` / `notes.md`. final.mp4(없으면 cut.mp4)를 사용자에게 보여준다.
확인용 정지 화면이 필요하면 `ffmpeg -ss 2 -i final.mp4 -frames:v 1 frame.png`.

피드백 반영 방법:
- **자막 문구 수정** → `subtitles.srt` 직접 고치고 `--mode burn`만 재실행 (재분석 불필요).
- **강조 단어** → srt에서 `==단어==`로 감싸거나 `--highlight 단어,단어`.
- **후킹 자막** → `--hook "…" --hook-seconds 4`.
- **자막 스타일(서체·색·크기·위치)** → `data/shorts_styles/growcircle.json` 수정 후 `--mode burn`.
  다른 무드가 필요하면 JSON을 복사해 새 프리셋(`--style <이름>`). 임시 조정은 `--sub-size`, `--sub-font`.
- **참조 쇼츠 스타일 맞추기** → 사용자가 참조 영상의 자막 장면 캡처를 올리면 서체 계열·색·테두리·
  위치를 읽어 프리셋 JSON을 고치고 다시 구워 나란히 비교한다(`data/shorts_styles/README.md`).
- **특정 컷 살리기/빼기** → `edit_plan.json`의 `segments` 배열을 손보고
  `--mode render`(해당 세그먼트) → `concat` → `burn` 재실행.
- **컷 기준 자체 변경** → 파라미터 바꿔 `--mode analyze`부터 다시.

## 5. 마무리 안내

BGM·효과음·전환은 캡컷 마무리 영역이다 — `notes.md`가 그 재료.
릴스 파이프라인(`reels_video.py`)의 산출물과 같은 관례: 초벌은 자동, 감성은 캡컷.

## 주의

- 원본은 절대 수정하지 않는다(모든 산출물은 `_shorts/` 폴더로). 드라이브 폴더 옆에 만들면
  산출물도 드라이브로 동기화돼 폰에서 바로 확인할 수 있다(용량은 수십 MB 수준).
- 촬영 원본·산출물 MP4는 **git에 커밋하지 않는다**(용량).
- 색 보정, 속도 조절, 트랜지션은 이 스킬 범위 밖 — 요청받아도 캡컷을 안내한다.
- 폰트: Pretendard가 없으면 설치된 한글 폰트로 대체된다. `data/fonts/`에 otf를 넣으면 설치 없이 쓴다.
