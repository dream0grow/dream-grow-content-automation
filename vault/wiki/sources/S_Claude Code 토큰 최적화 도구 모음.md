---
title: Claude Code 토큰 최적화 도구 모음
type: source
created: 2026-05-06
updated: 2026-05-06
sources:
  - "raw/clipings/ai_개발_자동화.md"
tags:
  - AI
  - ClaudeCode
  - 토큰최적화
  - 자동화
  - 5000IT·기술/5100AI
---

# Claude Code 토큰 최적화 도구 모음

Claude Code 운영 비용을 줄이고 컨텍스트 관리를 개선하는 오픈소스 도구 10선 정리.

## 토큰 절감 도구

| 도구 | 핵심 효과 | 저장소 |
|------|---------|--------|
| Caveman Claude | 정확도 손실 없이 출력 토큰 75% 감소 | github.com/juliusbrussee/caveman |
| RTK (Rust Token Killer) | 터미널 출력 필터링 프록시, 60-90% 감소 | github.com/rtk-ai/rtk |
| Code Review Graph | Tree-sitter 기반, 모노레포 49배 토큰 감소 | github.com/tirth8205/code-review-graph |
| Context Mode | SQLite 샌드박스화, 98% 컨텍스트 감소 | github.com/mksglu/context-mode |
| Claude Token Optimizer | 설정 프롬프트로 90% 토큰 절약 | github.com/nadimtuhin/claude-token-optimizer |
| Token Optimizer | 유령 토큰 사냥 + 컨텍스트 품질 복원 | github.com/alexgreensh/token-optimizer |
| Token Optimizer MCP | MCP 도구 캐싱·압축, 95%+ 감소 | github.com/ooples/token-optimizer-mcp |
| Claude Context | Zilliz 하이브리드 벡터 검색 MCP, 40% 비용 절감 | github.com/zilliztech/claude-context |
| Claude Token Efficient | CLAUDE.md 한 파일로 간결성 강제 | github.com/drona23/claude-token-efficient |
| Token Savior | 심볼 기반 코드 탐색, 97% 감소 | github.com/mibayy/token-savior |

## 부가 자료

- Hermes Agent — github.com/nousresearch/hermes-agent
- markitdown (마크다운 변환) — github.com/microsoft/markitdown
- markitdown-mcp — markitdown 패키지의 MCP 통합
- Hermes Workspace GUI — github.com/outsourc-e/hermes-workspace
- insane-search (네이버 등 수집) — github.com/fivetaku/insane-search

## 핵심 원리 — [[C_토큰 최적화 전략]]

토큰 최적화는 크게 4가지 접근으로 묶인다.
1. **출력 압축**: Caveman, RTK
2. **컨텍스트 격리**: Context Mode, Claude Context
3. **선택적 읽기**: Code Review Graph, Token Savior (심볼/그래프 기반)
4. **사전 설정 강제**: Token Optimizer, Token Efficient (CLAUDE.md/시스템 프롬프트)

## 관련 페이지

- [[C_토큰 최적화 전략]]

[출처:: [[ai_개발_자동화]]]
