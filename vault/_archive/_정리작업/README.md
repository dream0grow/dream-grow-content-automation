# 제텔카스텐 정리 작업 결과

## 처리 요약 (2026-05-09)

### 작업 1+2+3: 1단계 메모 시범 100개
- **처리 대상**: 처음 100개 (1149개 중)
- **rename**: 65건
- **frontmatter 표준화**: 100건
- **템플릿 섹션 추가**: 98건
- **백업 위치**: `/tmp/zettel_lv1_backup_20260509_022732`

### 1단계 메모 전체 통계
| 항목 | 처리 전 | 처리 후 | 비고 |
|------|--------|--------|------|
| 총 파일 | 1149 | 1150 | .DS_Store 포함 |
| 파일명에 줄바꿈 포함 | 198 | 196 | -2 (시범 100개 중 2개 처리) |
| 파일명에 깨진 자모 | 280 | 138 | -142 |

처리 후 깨끗한 파일명 비율: **710 → 816** (+106개 정상화)

### 작업 4: 2~5단계 정리
- **영어 중복 정리**: 10건 (예: `K-K_비고츠키_비계이론.md` → `K - 비고츠키 비계이론.md`)
- **frontmatter type 표준화**: 106건 (keyword/opinion/claim/second_brain)

## rename 패턴별 처리율

| 사유 | 발견 (전체) | 시범 100개 처리율 |
|------|------------|-----------------|
| newline_in_name | 198 | 약 1/3 (frontmatter title 있는 경우만) |
| broken_hangul | 133 | 약 1/2 |
| ai_response_dump | 2 | 0 (모두 SKIP) |
| leading_punct | 1 | 0 (SKIP) |
| too_short | 1 | 1 (성공) |

## 표준화된 frontmatter 양식
```yaml
---
title: 메모 제목 (완전한 명제)
type: memo  # memo | keyword | opinion | claim | second_brain
created: YYYY-MM-DD
sources: 출처 정보
tags: 태그
keywords: 키워드 (검색/연결용)
related: 관련 메모
status: draft | reviewed | linked
aliases: []
---
```

## 표준화된 본문 구조
```markdown
# 제목

## 핵심
- 한 문장 명제

## 인용
- 원전 인용

## 생각의 확장
- 적용/논증

## 연결
- [[관련 메모]]
```

## 다음 단계 (사용자 결정 필요)

### A. 1단계 메모 나머지 1049개 일괄 처리
같은 스크립트로 limit 제거하고 실행:
```bash
python3 zettel_organizer.py pilot --limit=2000
```
예상: rename 약 200~250건, frontmatter/template 1000건+

### B. SKIP된 파일 수동 처리
- `메모 내용이 보이지 않습니다`로 시작하는 AI 안내문 파일들 → 원본 raw 노트 다시 가져와서 재생성하거나 삭제 결정
- 깨진 자모로 끝났지만 본문도 부족한 파일들 → 사용자 직접 검토 권장

### C. 검증
- Obsidian에서 백링크 깨짐 여부 점검 (rename에 따른 [[old name]] 깨질 수 있음)
- 그래프뷰에서 고아 노드(연결 0) 확인

## 로그 파일
- `rename_log.md` — 1단계 메모 시범 100개 처리 로그
- `lv25_rename_log.md` — 2~5단계 영문 중복 정리 로그
- `lv25_fm_log.md` — 2~5단계 frontmatter 표준화 로그
- `zettel_organizer.py` — 정리 스크립트 (재실행 가능)
