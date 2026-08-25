# 쇼츠 자동 편집 설치 가이드 (맥북 / 윈도우)

DJI 오즈모 나노 촬영본을 `tools/shorts_edit.py`로 초벌 쇼츠까지 자동 편집하기 위한
1회 설치 안내. 편집은 전부 **로컬 컴퓨터**에서 돌아간다(원본을 클라우드에 올리지 않음).

## 1. 필수 — ffmpeg (영상 처리)

### 맥북
```bash
brew install ffmpeg
```
(Homebrew가 없으면 https://brew.sh 의 한 줄 설치 먼저)

### 윈도우
```powershell
winget install Gyan.FFmpeg
```
설치 후 터미널을 새로 열고 `ffmpeg -version`으로 확인.

## 2. 권장 — faster-whisper (자막 자동 생성)

```bash
pip install faster-whisper
```

- 없어도 편집(무음 컷·9:16 변환)은 되고, 자막 단계만 생략된다.
- 첫 실행 때 모델(기본 `small`, 약 500MB)을 자동 다운로드한다.
- 맥북 M칩/윈도우 CPU 모두 동작(int8 연산). 더 정확한 자막이 필요하면
  `--whisper-model medium`.

## 3. 선택 — Pretendard 폰트 (자막 스타일)

카드뉴스와 같은 Pretendard 볼드로 자막을 구우려면 폰트를 설치한다:
https://github.com/orioncactus/pretendard/releases → 설치 후 그대로 동작.
없으면 시스템 기본 폰트로 대체된다(`--sub-font`로 변경 가능).

## 4. 사용법

```bash
# SD카드 영상 하나
python3 tools/shorts_edit.py /Volumes/OsmoNano/DCIM/DJI_001/DJI_0012.MP4

# 폴더 통째로 (영상마다 <이름>_shorts/ 폴더 생성)
python3 tools/shorts_edit.py /Volumes/OsmoNano/DCIM/DJI_001/

# 컷 계획만 미리 보기 (렌더 없음)
python3 tools/shorts_edit.py 영상.mp4 --mode analyze
```

산출물(`<영상명>_shorts/`): `final.mp4`(자막 포함 초벌 쇼츠), `cut.mp4`(자막 전),
`subtitles.srt`, `edit_plan.json`(컷 계획 — 손으로 수정 가능), `notes.md`(캡컷 마무리 재료).

Claude Code/Cowork에서 이 저장소를 열고 **"쇼츠 편집해줘"**라고 하면
`dreamgrow-shorts-editor` 스킬이 위 과정을 대화로 진행한다(컷 계획 확인 → 렌더 → 피드백 반영).

## 5. 편집 규칙과 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--min-silence` | 0.9 | 이보다 긴 무음만 잘라냄(초) |
| `--pad` | 0.3 | 잘라낸 자리 앞뒤 여유(초). 강의 스타일은 0.5 |
| `--no-clap` | — | 박수=NG 컷 끄기 (박수 오탐 시) |
| `--fit` | crop | 9:16 변환: `crop`(중앙 크롭) / `blur`(블러 배경) |
| `--sub-size` | 15 | 자막 크기 |
| `--whisper-model` | small | 자막 모델 (`medium`이 더 정확, 느림) |

박수(👏) 한 번 = "방금 테이크 NG, 다시 갈게" 표시 — 박수 직전 발화가 자동으로 잘려나간다.
색 보정은 하지 않는다(원본 화질 유지). 오즈모 나노는 **일반 색상 프로파일**(D-Log M 아님)로
찍는 것을 권장 — D-Log는 색 보정이라는 수동 단계가 생긴다. 쇼츠 목적이면 세로 촬영이
크롭 손실이 없어 유리하다.
