# 쇼츠 자동 편집 설치 가이드 (맥북 / 윈도우)

DJI 오즈모 나노 촬영본을 `tools/shorts_edit.py`로 초벌 쇼츠까지 자동 편집하기 위한
1회 설치 안내. 편집은 전부 **로컬 컴퓨터**에서 돌아간다(원본을 클라우드에 올리지 않음).
클라우드 Claude 세션은 구글 드라이브·유튜브에 접근하지 못하므로, 실제 편집은 맥북의
Claude Code/Cowork(또는 터미널)에서 실행한다.

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

### 대안 — pip만으로
```bash
pip install imageio-ffmpeg
```
PATH에 ffmpeg가 없으면 엔진이 이 패키지의 동봉 바이너리를 자동으로 쓴다(ffprobe 없이도 동작).

## 2. 권장 — faster-whisper (자막 자동 생성)

```bash
pip install faster-whisper
```

- 없어도 편집(무음 컷·9:16 변환)은 되고, 자막 단계만 생략된다.
- 첫 실행 때 모델(기본 `small`, 약 500MB)을 자동 다운로드한다.
- 맥북 M칩/윈도우 CPU 모두 동작(int8 연산). 더 정확한 자막이 필요하면
  `--whisper-model medium`.

## 3. 선택 — Pretendard 폰트 (자막 서체)

프리셋 기본 서체는 Pretendard 볼드다. 둘 중 하나:
- 시스템 설치: https://github.com/orioncactus/pretendard/releases
- 설치 없이: 받은 otf를 저장소 `data/fonts/`에 넣는다(엔진이 자동 인식).
없으면 설치된 한글 폰트(Apple SD Gothic Neo, 맑은 고딕 등)로 대체된다.

## 4. 사용법

```bash
# 촬영본 폴더를 한 번 지정해 두면 이름만으로 실행할 수 있다
export DG_OSMO_DIR="$HOME/Library/CloudStorage/GoogleDrive-leehg0211@gmail.com/내 드라이브/DJI_오즈모 영상"

# 영상 하나 (이름만, LRF/WAV는 자동 제외)
python3 tools/shorts_edit.py DJI_20260914072454_0008_D

# 상단 후킹 자막까지
python3 tools/shorts_edit.py DJI_20260914072454_0008_D --hook "현직 초등교사가 알려주는|==학교 가기 싫다는 아이=="

# 폴더 통째로 (영상마다 <이름>_shorts/ 폴더 생성)
python3 tools/shorts_edit.py "/Volumes/OsmoNano/DCIM/DJI_001/"

# 컷 계획만 미리 보기 (렌더 없음)
python3 tools/shorts_edit.py 영상.mp4 --mode analyze
```

산출물(`<영상명>_shorts/`): `final.mp4`(자막 포함 초벌 쇼츠), `cut.mp4`(자막 전),
`subtitles.srt`(문구 수정용), `subtitles.ass`(실제 구운 스타일), `edit_plan.json`(컷 계획 — 손으로 수정 가능),
`notes.md`(다듬기·캡컷 재료).

Claude Code/Cowork에서 이 저장소를 열고 **"쇼츠 편집해줘"**라고 하면
`dreamgrow-shorts-editor` 스킬이 위 과정을 대화로 진행한다(컷 계획 확인 → 렌더 → 피드백 반영).

## 5. 편집 규칙과 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--min-silence` | 0.9 | 이보다 긴 무음만 잘라냄(초) |
| `--pad` | 0.3 | 잘라낸 자리 앞뒤 여유(초). 강의 스타일은 0.5 |
| `--no-clap` | — | 박수=NG 컷 끄기 (박수 오탐 시) |
| `--fit` | crop | 9:16 변환: `crop`(중앙 크롭) / `blur`(블러 배경) |
| `--style` | growcircle | 자막 스타일 프리셋(`data/shorts_styles/*.json`) 또는 JSON 경로 |
| `--hook` | — | 상단 후킹 자막. `\|`로 줄바꿈, `==단어==` 강조 |
| `--hook-seconds` | 0(내내) | 후킹 자막 노출 시간(초) |
| `--highlight` | — | 자동 강조 단어(쉼표 구분) |
| `--max-chars` | 프리셋 | 자막 한 줄 글자 수 |
| `--sub-size` / `--sub-font` | 프리셋 | 임시 덮어쓰기 (1080×1920 기준 px) |
| `--whisper-model` | small | 자막 모델 (`medium`이 더 정확, 느림) |

박수(👏) 한 번 = "방금 테이크 NG, 다시 갈게" 표시 — 박수 직전 발화가 자동으로 잘려나간다.
색 보정은 하지 않는다(원본 화질 유지). 오즈모 나노는 **일반 색상 프로파일**(D-Log M 아님)로
찍는 것을 권장 — D-Log는 색 보정이라는 수동 단계가 생긴다. 쇼츠 목적이면 세로 촬영이
크롭 손실이 없어 유리하다.

## 6. 자막 스타일 다듬기

스타일은 `data/shorts_styles/growcircle.json` 한 파일이 정한다(서체·색·테두리·위치·글자 수·후킹).
참조 쇼츠와 맞추려면 참조 영상의 자막 장면 캡처를 Claude에 보여주고 프리셋을 고친 뒤
`--mode burn`만 다시 실행한다(재분석·재렌더 없음). 자세한 키 설명은 `data/shorts_styles/README.md`.
