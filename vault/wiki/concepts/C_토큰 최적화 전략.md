---
title: 토큰 최적화 전략
type: concept
created: 2026-05-06
updated: 2026-05-06
sources:
  - "raw/clipings/ai_개발_자동화.md"
  - "raw/clipings/ai_자동화+업그레이드.md"
tags:
  - AI
  - ClaudeCode
  - 토큰최적화
  - 5000IT·기술/5100AI
---

# 토큰 최적화 전략

LLM(Claude Code 등) 운영 시 컨텍스트 비용과 응답 비용을 절감하는 4가지 접근.

## 4가지 접근

### 1. 출력 압축
모델이 생성하는 응답 토큰 자체를 줄이는 방식.
- Caveman Claude (정확도 손실 없이 출력 75% 감소)
- RTK 터미널 출력 필터링 프록시

### 2. 컨텍스트 격리
원시 출력을 컨텍스트에서 분리해 외부 저장소에 보관.
- Context Mode (SQLite 샌드박스)
- Claude Context (Zilliz 하이브리드 벡터 검색)

### 3. 선택적 읽기
거대 코드베이스에서 필요한 부분만 읽도록 유도.
- Code Review Graph (Tree-sitter 그래프)
- Token Savior (심볼 기반 코드 탐색)

### 4. 사전 설정 강제
프로젝트 단위에서 간결성/효율성을 시스템 프롬프트로 강제.
- Claude Token Optimizer
- Claude Token Efficient (CLAUDE.md 한 파일)
- Token Optimizer MCP

## 적용 우선순위

작은 프로젝트는 4번 사전 설정만으로 충분. 모노레포·대규모 코드베이스는 3번 선택적 읽기 + 2번 컨텍스트 격리 조합 효과가 크다.

## 관련 개념

- [[C_측정과 판단의 분리]]
- [[S_Claude Code 토큰 최적화 도구 모음]]
