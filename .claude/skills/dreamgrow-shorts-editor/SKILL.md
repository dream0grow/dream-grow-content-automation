---
name: dreamgrow-shorts-editor
description: DJI 오즈모 나노 등으로 촬영한 영상을 초벌 쇼츠(9:16 MP4)로 자동 편집한다 — 무음 컷(앞뒤 여유) + 박수=NG 컷 + Whisper 자막 + 1080x1920 변환. "쇼츠 편집해줘", "오즈모 영상 편집", "촬영본 쇼츠로", "무음 잘라서 쇼츠", "SD카드 영상 편집", "쇼츠 만들어줘(촬영본 기반)" 같은 요청이면 반드시 이 스킬을 사용한다. 엔진은 tools/shorts_edit.py — 색 보정은 하지 않고 원본 화질을 유지한다. Cowork 45초 bash 제한 환경에서는 조각 렌더링(--mode render --segment N)으로 동작한다.
---

# 드림그로우 쇼츠 편집 루프

촬영 원본(오즈모 나노 MP4 등)을 **분석 → 컷 계획 확인 → 렌더 → 자막 → 피드백 반영**으로
초벌 쇼츠까지 만드는 반복 루프. 엔진은 `tools/shorts_edit.py` 하나다 — 편집 규칙을 여기서
새로 짓지 말 것. 코드 기본값이 곧 확정 스펙이다.

편집 규칙(video-lecture-editor와 동일 철학):
- 무음 구간 제거, 잘라낸 자리 앞뒤 `--pad`(기본 0.3초) 여유는 남긴다.
- **박수 소리 = 재촬영(NG) 표시** → 박수 직전 테이크를 잘라낸다.
- 색 보정 없음 — 원본 화질 그대로. 9:16(1080×1920) 변환과 자막만.

## 0. 사전 확인 (첫 실행 시 1회)

```bash
ffmpeg -version && ffprobe -version   # 없으면 docs/shorts-edit-setup.md 안내
python3 -c "import faster_whisper" 2>/dev/null || echo "자막용: pip install faster-whisper"
```

ffmpeg가 없으면 **편집 자체가 불가** — 설치 안내 후 중단.
faster-whisper가 없으면 자막만 생략된다(편집은 진행) — 사용자에게 알리고 계속.

## 1. 영상 위치 확인

사용자에게 촬영본 경로를 물어본다(파일 하나 또는 SD카드/폴더).
오즈모 나노 SD카드는 보통 `DCIM/DJI_001/` 아래에 `DJI_*.MP4`로 들어 있다.

## 2. 분석 → 컷 계획을 반드시 먼저 보여준다

```bash
python3 tools/shorts_edit.py <영상> --mode analyze
```

출력되는 세그먼트 목록·박수(NG) 감지 결과·최종 길이를 사용자에게 보여주고 확인받는다.
- 박수 오탐이 있으면 `--no-clap` 또는 `edit_plan.json`에서 해당 컷만 되돌리기.
- 컷이 너무 잘게/성기게 나오면 `--min-silence`(기본 0.9초)·`--pad`(기본 0.3초) 조정 후 재분석.
- 강의 스타일(여유 있게)을 원하면 `--pad 0.5`.
- 편집 후 180초 초과면 여러 편 분할을 제안한다.

## 3. 렌더 — 환경에 맞는 방식으로

**로컬 터미널(제한 없음)**: 한 번에 전부.
```bash
python3 tools/shorts_edit.py <영상>            # analyze→render→concat→subs→burn
```

**Cowork 45초 bash 제한 환경**: 조각 렌더링 — 세그먼트 하나씩, 단계별로.
```bash
python3 tools/shorts_edit.py <영상> --mode render --segment 0   # 세그먼트별 반복
python3 tools/shorts_edit.py <영상> --mode concat
python3 tools/shorts_edit.py <영상> --mode subs                 # Whisper (수십 초 걸릴 수 있음)
python3 tools/shorts_edit.py <영상> --mode burn
```
세그먼트 하나가 45초를 넘길 만큼 길면 `run_in_background`로 실행한다.

가로 촬영본인데 인물이 중앙에 없으면 `--fit blur`(블러 배경 레터박스)를 제안한다.

## 4. 결과 확인 → 피드백 루프

`<영상명>_shorts/` 안: `final.mp4`(자막 포함) / `cut.mp4`(자막 전) / `subtitles.srt` /
`edit_plan.json` / `notes.md`. final.mp4(없으면 cut.mp4)를 사용자에게 보여준다.

피드백 반영 방법:
- **자막 문구 수정** → `subtitles.srt` 직접 고치고 `--mode burn`만 재실행 (재분석 불필요).
- **자막 스타일** → `--sub-size`, `--sub-font` 바꿔 `--mode burn` 재실행.
- **특정 컷 살리기/빼기** → `edit_plan.json`의 `segments` 배열을 손보고
  `--mode render`(해당 세그먼트) → `concat` → `burn` 재실행.
- **컷 기준 자체 변경** → 파라미터 바꿔 `--mode analyze`부터 다시.

## 5. 마무리 안내

BGM·효과음·후킹 자막(표지형 큰 자막)은 캡컷 마무리 영역이다 — `notes.md`가 그 재료.
릴스 파이프라인(`reels_video.py`)의 산출물과 같은 관례: 초벌은 자동, 감성은 캡컷.

## 주의

- 원본은 절대 수정하지 않는다(모든 산출물은 `_shorts/` 폴더로).
- 촬영 원본·산출물 MP4는 **git에 커밋하지 않는다**(용량). 볼트/저장소 밖 경로 권장.
- 색 보정, 속도 조절, 트랜지션은 이 스킬 범위 밖 — 요청받아도 캡컷을 안내한다.
