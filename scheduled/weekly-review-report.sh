#!/bin/bash
# 주간 콘텐츠 리뷰 보고서 생성
# 매주 일요일 20:00 실행

REVIEW_DIR="/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템/08 리뷰"
THREAD_DIR="/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템/07 스레드"
SCRIPT_DIR="/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템/05 제작/52 원고"
PERF_DIR="/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템/06 운영/61 성과 기록"
LOG_DIR="/Users/lhg/Library/CloudStorage/Dropbox/1.한결/나/ㄱ.AI/content-automation/scheduled/logs"

mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
REPORT="$LOG_DIR/weekly-report-$DATE.md"

echo "# 주간 콘텐츠 보고서 ($DATE)" > "$REPORT"
echo "" >> "$REPORT"

# 리뷰 대기 파일
echo "## 08 리뷰/ 대기 파일" >> "$REPORT"
if [ -d "$REVIEW_DIR" ]; then
    COUNT=$(find "$REVIEW_DIR" -name "*.md" -maxdepth 1 | wc -l | tr -d ' ')
    echo "- 리뷰 대기: ${COUNT}개" >> "$REPORT"
    if [ "$COUNT" -gt 0 ]; then
        find "$REVIEW_DIR" -name "*.md" -maxdepth 1 -exec basename {} \; >> "$REPORT"
    fi
else
    echo "- 폴더 없음" >> "$REPORT"
fi
echo "" >> "$REPORT"

# 이번 주 생성된 스레드
echo "## 이번 주 스레드" >> "$REPORT"
find "$THREAD_DIR" -name "*.md" -newer "$LOG_DIR/.last-weekly" 2>/dev/null | wc -l | xargs -I{} echo "- 새 스레드: {}개" >> "$REPORT"
echo "" >> "$REPORT"

# 이번 주 생성된 원고
echo "## 이번 주 원고" >> "$REPORT"
find "$SCRIPT_DIR" -name "*.md" -newer "$LOG_DIR/.last-weekly" 2>/dev/null | wc -l | xargs -I{} echo "- 새 원고: {}개" >> "$REPORT"
echo "" >> "$REPORT"

# 타임스탬프 갱신
touch "$LOG_DIR/.last-weekly"

echo "주간 보고서 생성: $REPORT"
cat "$REPORT"
