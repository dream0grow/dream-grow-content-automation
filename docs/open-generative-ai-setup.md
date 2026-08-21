# Open Generative AI 설치 + 릴스(숏폼) 영상 자동화 가이드

> 저장소: https://github.com/Anil-matcha/Open-Generative-AI (MIT 라이선스)
> 마지막 갱신: 2026-08-19

## 무엇인가

Open Generative AI는 400개 이상의 이미지/영상 AI 모델(Seedance, Kling, Veo,
Wan, Hailuo, Sora 등)을 한 화면에서 쓰는 오픈소스 스튜디오 앱이다(Next.js/Electron).
모델 호출은 전부 **Muapi.ai**라는 통합 API 게이트웨이 하나로 나간다 —
키 하나만 있으면 모든 모델을 쓸 수 있고, 쓴 만큼만 과금된다.

우리 파이프라인은 이 구조를 그대로 가져와 두 갈래로 쓴다.

1. **자동 (파이프라인)**: `orchestrator/reels_video.py`가 릴스 원고의 B-roll
   장면 목록을 읽어 장면별 9:16 클립을 Muapi API로 생성하고 ffmpeg로 이어
   붙여 초벌 릴스(reel_draft.mp4)를 만든다. GUI 앱 설치 없이도 동작한다.
2. **수동 (GUI 스튜디오)**: 마음에 안 드는 장면을 데스크톱 앱에서 모델을
   바꿔가며 다시 뽑거나, 표지용 이미지·립싱크 등 실험할 때 쓴다.

## 1회 설정 (사용자 액션)

### ① Muapi API 키 발급

1. https://muapi.ai 가입 → API Key 발급 (크레딧 충전형, 쓴 만큼 과금)
2. GitHub 저장소 → Settings → Secrets and variables → Actions →
   `MUAPI_API_KEY` 등록

### ② (선택) GUI 스튜디오를 내 Mac에 설치

두 가지 중 편한 쪽:

- **설치 스크립트**: `bash tools/setup_open_generative_ai.sh`
  (기본 `~/Open-Generative-AI`에 클론 + `npm run setup`까지 자동.
  Node.js LTS 필요 — https://nodejs.org)
  - 웹 버전 실행: `npm run dev` → http://localhost:3000
  - 데스크톱 앱: `npm run electron:dev`
- **원클릭 인스톨러**: 저장소 릴리스 페이지에서 macOS용 dmg 다운로드
  (Node.js 불필요)

첫 실행 후 Settings 화면에 ①의 Muapi 키를 입력하면 바로 생성 가능.

## 릴스 영상 자동 생성 사용법

### GitHub Actions (권장 — 폰에서도 가능)

Actions 탭 → **test-reels-video** → Run workflow:

| 입력 | 설명 |
|------|------|
| `script` | 릴스 원고 파일명 (`05 리뷰/대기`, 부분 일치 가능. 예: `원고_릴스_훈육_좋은+훈육`) |
| `topic` | 원고 없이 주제만으로 생성 (script를 비웠을 때) |
| `max_scenes` | 최대 장면 수 (기본 7) |
| `dry_run` | `true`면 장면·프롬프트만 뽑음 (Muapi 키/과금 없음) |

완료되면 실행 페이지의 **reels-video 아티팩트**에서 내려받는다:

- `reel_draft.mp4` — 장면들을 이어 붙인 초벌 릴스 (1080×1920, 무음)
- `scene_01.mp4 …` — 장면별 개별 클립 (마음에 안 드는 것만 교체 가능)
- `notes.md` — 장면표 + 내레이션 전문 (캡컷 마무리 재료)
- `reels_plan.json` — 프롬프트/모델 기록

### 로컬 CLI

```bash
python3 -m orchestrator.reels_video --script "원고_릴스_훈육_좋은+훈육"   # 원고 기반
python3 -m orchestrator.reels_video --topic "아이 훈육 3단계"             # 주제 기반
python3 -m orchestrator.reels_video --script ... --dry-run                # 프롬프트만
```

### 마무리는 사람이 (캡컷)

AI가 만드는 것은 **B-roll 배경 영상까지**다. `notes.md`의 내레이션을
자막·음성으로 얹고, BGM과 리드마그넷 CTA 화면을 붙이는 것은 캡컷에서
사람이 한다. 원고의 타임코드와 장면 순서가 그대로 유지되므로 얹기만 하면 된다.

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MUAPI_API_KEY` | (없음) | Muapi.ai API 키. 없으면 `--dry-run`만 가능 |
| `DG_REELS_VIDEO_MODEL` | `seedance-lite-t2v` | text-to-video 모델 (9:16 지원 모델이면 교체 가능: `kling-v2.5-turbo-pro-t2v`, `wan2.2-5b-fast-t2v` 등) |
| `DG_REELS_VIDEO_RESOLUTION` | `720p` | 480p/720p/1080p (모델별 상이) |
| `DG_REELS_SCENE_SECONDS` | `5` | 장면당 클립 길이(초) |
| `DG_REELS_MAX_SCENES` | `7` | 한 번에 생성할 최대 장면 수 (과금 상한) |

## 비용 감각

기본 모델(seedance-lite-t2v, 720p, 5초)은 클립당 수십 원 수준이다.
릴스 1편(장면 6개) ≈ 몇백 원. `max_scenes`가 과금 상한 역할을 한다.
모델을 Veo/Sora급으로 올리면 클립당 수천 원까지 올라가니, 초벌은 lite로
뽑고 마음에 드는 장면만 상위 모델로 재생성하는 것을 권장한다.

## 주의

- 생성 클립은 실사풍이지만 AI 생성물이다. 실제 인물/기관처럼 보이게
  쓰거나 실촬영으로 오인시키는 연출은 피하고, 채널 정책에 맞게
  AI 생성 표기를 한다.
- Muapi 쪽 모델은 수시로 추가/폐기된다. 모델 에러가 나면
  `DG_REELS_VIDEO_MODEL`을 다른 9:16 지원 모델로 바꿔 재실행.
