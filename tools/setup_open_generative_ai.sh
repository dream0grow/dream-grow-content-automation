#!/usr/bin/env bash
# Open Generative AI 로컬 설치 스크립트 (Mac/리눅스)
#
# GUI 스튜디오(이미지/영상/립싱크)를 내 컴퓨터에 설치한다. 파이프라인의
# 릴스 자동 생성(orchestrator/reels_video.py)은 이 앱 없이도 동작하지만,
# 같은 Muapi 키로 앱에서 장면을 수동 재생성/실험할 때 쓴다.
# 자세한 안내: docs/open-generative-ai-setup.md
#
# 사용법:  bash tools/setup_open_generative_ai.sh [설치경로]   (기본 ~/Open-Generative-AI)
set -euo pipefail

DEST="${1:-$HOME/Open-Generative-AI}"
REPO="https://github.com/Anil-matcha/Open-Generative-AI.git"

if ! command -v git >/dev/null; then echo "git이 필요합니다"; exit 1; fi
if ! command -v npm >/dev/null; then
  echo "Node.js(npm)가 필요합니다 — https://nodejs.org 에서 LTS 설치 후 재실행"; exit 1
fi

if [ -d "$DEST/.git" ]; then
  echo "이미 클론됨 — 업데이트: $DEST"
  git -C "$DEST" pull --ff-only
  git -C "$DEST" submodule update --init --recursive
else
  echo "클론: $REPO → $DEST"
  git clone --recurse-submodules "$REPO" "$DEST"
fi

cd "$DEST"
echo "의존성 설치 (npm run setup)…"
npm run setup

cat <<'EOF'

✅ 설치 완료. 실행 방법:
  웹 버전:      cd ~/Open-Generative-AI && npm run dev       (브라우저 http://localhost:3000)
  데스크톱 앱:  cd ~/Open-Generative-AI && npm run electron:dev

첫 실행 후 Settings에서 Muapi API 키를 입력하세요 (발급: https://muapi.ai).
같은 키를 GitHub Secrets의 MUAPI_API_KEY로 등록하면 파이프라인
(test-reels-video 워크플로우)이 릴스 원고에서 영상까지 자동 생성합니다.
EOF
