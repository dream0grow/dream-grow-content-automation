from __future__ import annotations

from .base import GeneratedContent, GeneratorContext, LLMCallable

MAGNET_TYPES = {
    "checklist": "체크리스트 (15~20개 항목, 카테고리별 묶음)",
    "concept_map": "개념 지도 (핵심 개념 → 하위 개념 → 적용 예시)",
    "action_guide": "실천 가이드 (7일 또는 4주 단위 일자별 행동)",
    "worksheet": "워크시트 (아이와 부모가 함께 채우는 빈칸)",
    "roadmap": "로드맵 (단계별 학습/성장 경로)",
}

MAGNET_SYSTEM = """당신은 {brand}의 무료 자료(리드마그넷) 제작자입니다.
A4 1~3페이지로 인쇄해 사용할 수 있는 마크다운을 작성합니다.

## 형식: {magnet_type_desc}

## 규칙
- 표지(제목, 부제, 사용 안내) → 본문 → 마지막에 짧은 행동 유도
- 시각적 위계가 분명한 마크다운 (H1, H2, 체크박스 - [ ], 표)
- 본문 끝: "{brand_signature}"
"""


def generate(ctx: GeneratorContext, llm: LLMCallable) -> GeneratedContent:
    magnet_type = ctx.magnet_type or "action_guide"
    desc = MAGNET_TYPES.get(magnet_type, MAGNET_TYPES["action_guide"])
    system = MAGNET_SYSTEM.format(
        brand=ctx.brand.name,
        magnet_type_desc=desc,
        brand_signature=ctx.brand.brand_signature,
    )
    prompt = f"주제: {ctx.topic}\n카테고리: {ctx.category or ''}\n유형: {magnet_type}"
    return llm(prompt, system=system, model="sonnet", max_tokens=4000)
