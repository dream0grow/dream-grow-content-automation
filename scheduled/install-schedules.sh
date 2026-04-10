#!/bin/bash
# Dream_Grow 정기 작업 설치 스크립트
# launchd에 plist 등록

SCHED_DIR="/Users/lhg/Library/CloudStorage/Dropbox/1.한결/나/ㄱ.AI/content-automation/scheduled"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$SCHED_DIR/logs"

mkdir -p "$LOG_DIR"
mkdir -p "$LAUNCH_DIR"

# 기존 작업 언로드 (에러 무시)
launchctl unload "$LAUNCH_DIR/com.dreamgrow.diff-learn.plist" 2>/dev/null
launchctl unload "$LAUNCH_DIR/com.dreamgrow.weekly-review.plist" 2>/dev/null

# plist 복사
cp "$SCHED_DIR/daily-diff-learn.plist" "$LAUNCH_DIR/com.dreamgrow.diff-learn.plist"
cp "$SCHED_DIR/weekly-review-report.plist" "$LAUNCH_DIR/com.dreamgrow.weekly-review.plist"

# 실행 권한
chmod +x "$SCHED_DIR/weekly-review-report.sh"

# 등록
launchctl load "$LAUNCH_DIR/com.dreamgrow.diff-learn.plist"
launchctl load "$LAUNCH_DIR/com.dreamgrow.weekly-review.plist"

# 타임스탬프 초기화
touch "$LOG_DIR/.last-weekly"

echo "=== 정기 작업 설치 완료 ==="
echo ""
echo "1. diff-learn (매일 21:00)"
echo "   - 08 리뷰/에서 '리뷰완료' 파일 감지"
echo "   - AI 원본과 diff 비교 → Honcho에 패턴 저장"
echo "   - 로그: $LOG_DIR/diff-learn.log"
echo ""
echo "2. weekly-review (매주 일요일 20:00)"
echo "   - 리뷰 대기 파일 수, 이번 주 스레드/원고 수 집계"
echo "   - 보고서: $LOG_DIR/weekly-report-YYYY-MM-DD.md"
echo ""
echo "확인: launchctl list | grep dreamgrow"
echo "해제: launchctl unload ~/Library/LaunchAgents/com.dreamgrow.*.plist"
