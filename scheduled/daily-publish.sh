#!/bin/bash
# Dream_Grow 자동 발행 + 캘린더 갱신
# 매일 08:00 실행

SCRIPT_DIR="/Users/lhg/Library/CloudStorage/Dropbox/1.한결/나/ㄱ.AI/content-automation"
LOG_DIR="$SCRIPT_DIR/scheduled/logs"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

mkdir -p "$LOG_DIR"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 자동 발행 시작 ===" >> "$LOG_DIR/publish.log"

# 1. 발행대기 콘텐츠 발행 (dry-run 모드 - 실제 발행은 --publish 플래그로)
cd "$SCRIPT_DIR"
$PYTHON threads_publisher.py --dry-run >> "$LOG_DIR/publish.log" 2>&1

# 2. 주간 캘린더 갱신
$PYTHON publish_calendar.py >> "$LOG_DIR/publish.log" 2>&1

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 완료 ===" >> "$LOG_DIR/publish.log"
echo "" >> "$LOG_DIR/publish.log"
