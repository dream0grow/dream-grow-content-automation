# 네이버 금융 시황정보 리포트 자동 수집·분석

## 개요
매일 네이버 금융 시황정보 리포트 페이지에서 당일 리포트를 수집하고,
PDF를 다운로드하여 AI로 핵심 내용과 투자 인사이트를 정리합니다.

## 실행 방법

```bash
cd /home/ubuntu/naver_research
python3 collect_and_analyze.py          # 오늘 날짜 실행
python3 collect_and_analyze.py 26.06.30  # 특정 날짜 지정
```

## 결과물 저장 위치
- PDF 원본: /home/ubuntu/naver_research/reports/YYYYMMDD/
- 분석 결과: /home/ubuntu/naver_research/summaries/YYYYMMDD_market_report.md
- 메타데이터: /home/ubuntu/naver_research/summaries/YYYYMMDD_metadata.json
- 실행 로그: /home/ubuntu/naver_research/logs/YYYYMMDD.log

## 자동화 스케줄
- 평일(월~금) 오전 9시 (KST) 자동 실행
- Manus 스케줄러를 통해 관리됨

## 분석 구조
1. 공통 핵심 내용: 여러 리포트에서 공통으로 언급된 거시경제, 증시 흐름, 섹터 동향
2. 개별 인사이트: 특정 증권사만의 독자적 분석 및 투자 유용 정보
