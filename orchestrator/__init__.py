"""드림그로우 v2 오케스트레이터 - 옵시디언 볼트 기반 멀티 에이전트 파이프라인

옵시디언 볼트(vault/파이프라인/)를 단일 진실 공급원으로 두고,
GitHub Actions cron이 30분마다 stage/status를 읽어 다음 에이전트를 실행한다.

상세 설계: docs/ARCHITECTURE_V2.md
"""
