#!/bin/bash
# Dream_Grow 정기 작업 + 팀 에이전트 설치 스크립트
# launchd에 plist 등록

SCHED_DIR="/Users/lhg/Library/CloudStorage/Dropbox/1.한결/나/ㄱ.클로드코드_드림그로우/content-automation/scheduled"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$SCHED_DIR/logs"

mkdir -p "$LOG_DIR"
mkdir -p "$LAUNCH_DIR"

# 기존 작업 언로드 (에러 무시)
launchctl unload "$LAUNCH_DIR/com.dreamgrow.diff-learn.plist" 2>/dev/null
launchctl unload "$LAUNCH_DIR/com.dreamgrow.weekly-review.plist" 2>/dev/null
launchctl unload "$LAUNCH_DIR/com.dreamgrow.team-content.plist" 2>/dev/null
launchctl unload "$LAUNCH_DIR/com.dreamgrow.team-knowledge.plist" 2>/dev/null
launchctl unload "$LAUNCH_DIR/com.dreamgrow.team-book.plist" 2>/dev/null
launchctl unload "$LAUNCH_DIR/com.dreamgrow.scheduled-publish.plist" 2>/dev/null

# plist 복사
cp "$SCHED_DIR/daily-diff-learn.plist" "$LAUNCH_DIR/com.dreamgrow.diff-learn.plist"
cp "$SCHED_DIR/weekly-review-report.plist" "$LAUNCH_DIR/com.dreamgrow.weekly-review.plist"
cp "$SCHED_DIR/team-content.plist" "$LAUNCH_DIR/com.dreamgrow.team-content.plist"
cp "$SCHED_DIR/team-knowledge.plist" "$LAUNCH_DIR/com.dreamgrow.team-knowledge.plist"
cp "$SCHED_DIR/team-book.plist" "$LAUNCH_DIR/com.dreamgrow.team-book.plist"
cp "$SCHED_DIR/scheduled-publish.plist" "$LAUNCH_DIR/com.dreamgrow.scheduled-publish.plist"

# 실행 권한
chmod +x "$SCHED_DIR/weekly-review-report.sh"

# 등록
launchctl load "$LAUNCH_DIR/com.dreamgrow.diff-learn.plist"
launchctl load "$LAUNCH_DIR/com.dreamgrow.weekly-review.plist"
launchctl load "$LAUNCH_DIR/com.dreamgrow.team-content.plist"
launchctl load "$LAUNCH_DIR/com.dreamgrow.team-knowledge.plist"
launchctl load "$LAUNCH_DIR/com.dreamgrow.team-book.plist"
launchctl load "$LAUNCH_DIR/com.dreamgrow.scheduled-publish.plist"

# 타임스탬프 초기화
touch "$LOG_DIR/.last-weekly"

echo "=== Dream_Grow 스케줄 설치 완료 ==="
echo ""
echo "--- 정기 작업 ---"
echo "1. diff-learn (매일 21:00)"
echo "   - 리뷰완료 파일 diff 분석 → Honcho 학습"
echo ""
echo "2. weekly-review (매주 일 20:00)"
echo "   - 콘텐츠 생산량/리뷰 대기 집계"
echo ""
echo "--- 팀 에이전트 ---"
echo "3. team-content (매일 04:00)"
echo "   - 스레드 + 릴스 + 리드마그넷 3세트 생산"
echo "   - 리뷰: 매일 아침 7~8시"
echo ""
echo "4. team-knowledge (매주 금 11:00)"
echo "   - 제텔카스텐 + wiki + 백링크"
echo "   - 리뷰: 금요일 오후"
echo ""
echo "5. team-book (매주 토 05:00)"
echo "   - 콘텐츠 → 책 챕터 초안"
echo "   - 리뷰: 주말"
echo ""
echo "6. scheduled-publish (매시 정각)"
echo "   - 발행시간 도달한 리뷰완료 파일 → Threads API 발행"
echo "   - 05 리뷰/완료/ → 64 발행완료/ 이동"
echo ""
echo "--- skill-updater ---"
echo "각 팀 실행 후 자동으로 diff학습 + Honcho 업데이트 + 캘린더 갱신"
echo ""
echo "확인: launchctl list | grep dreamgrow"
echo "해제: launchctl unload ~/Library/LaunchAgents/com.dreamgrow.*.plist"
echo "수동 실행: python3 agents/team_runner.py content|knowledge|book|skill"
