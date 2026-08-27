#!/bin/bash
# aside CLI 설치 스크립트 (https://docs.aside.com/help/developers)
# 클라우드(Claude Code on the web) 세션이나 로컬에서 실행한다.
# 전제: 클라우드에서는 환경 네트워크 정책에 releases.aside.com 허용이 필요.
set -uo pipefail

# 이미 설치돼 있으면 끝 (멱등 — 여러 번 실행해도 안전)
for p in "$(command -v aside 2>/dev/null)" "$HOME/.aside/bin/aside" "$HOME/.local/bin/aside" /usr/local/bin/aside; do
  if [ -n "$p" ] && [ -x "$p" ]; then
    echo "aside CLI 이미 설치됨: $p"
    exit 0
  fi
done

# 공식 설치 스크립트를 먼저 파일로 받은 뒤 실행 (곧바로 | bash 하지 않음)
installer="$(mktemp)"
if ! curl -fsSL --max-time 120 https://releases.aside.com/install.sh -o "$installer"; then
  echo "❌ releases.aside.com 접근 실패." >&2
  echo "   클라우드 세션이라면 claude.ai/code 환경 설정의 네트워크 정책에" >&2
  echo "   releases.aside.com 도메인 허용을 추가한 뒤 새 세션에서 다시 실행하세요." >&2
  rm -f "$installer"
  exit 1
fi

if ! bash "$installer"; then
  echo "❌ aside 설치 스크립트 실행 실패." >&2
  rm -f "$installer"
  exit 1
fi
rm -f "$installer"

# 설치 위치 확인 + PATH 안내
for p in "$(command -v aside 2>/dev/null)" "$HOME/.aside/bin/aside" "$HOME/.local/bin/aside" /usr/local/bin/aside; do
  if [ -n "$p" ] && [ -x "$p" ]; then
    echo "✅ aside CLI 설치 완료: $p"
    if ! command -v aside >/dev/null 2>&1; then
      echo "   PATH에 없으므로 다음을 실행하세요: export PATH=\"$(dirname "$p"):\$PATH\""
    fi
    exit 0
  fi
done

echo "⚠️ 설치는 끝났지만 aside 실행 파일 위치를 찾지 못함 — 설치 로그를 확인하세요." >&2
exit 1
