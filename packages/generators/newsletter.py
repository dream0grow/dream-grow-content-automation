from __future__ import annotations

from .base import GeneratedContent, GeneratorContext, LLMCallable

NEWSLETTER_SYSTEM = """당신은 {brand}의 주간 뉴스레터 작가입니다.
구독자는 {audience}이며, 한 호당 6,000~7,000자 사이의 깊이 있는 글을 씁니다.

## 구조
1. 오프닝 — 한 가족의 짧은 장면으로 시작
2. 본문 1 — 이번 주 핵심 주제 (개념 정의 + 부모가 자주 오해하는 지점)
3. 본문 2 — 학교 현장에서 본 사례 (대화 인용 포함)
4. 본문 3 — 집에서 적용할 수 있는 3단계 방법
5. 마무리 기원문 + {brand_signature}

## 톤
- 존댓말, 차분한 글말체. 학자명 나열 금지.
- 이모지 절대 금지. 출처 없는 통계 금지.
"""


def generate(ctx: GeneratorContext, llm: LLMCallable) -> GeneratedContent:
    system = NEWSLETTER_SYSTEM.format(
        brand=ctx.brand.name,
        audience=ctx.brand.audience,
        brand_signature=ctx.brand.brand_signature,
    )
    if ctx.style_context:
        system += f"\n\n## 스타일 메모리\n{ctx.style_context}"
    refs = "\n\n".join(f"### 참고 자료\n{r}" for r in ctx.reference_bodies)
    prompt = f"주제: {ctx.topic}\n카테고리: {ctx.category or ''}\n\n{refs}\n\n위 주제로 뉴스레터를 작성해주세요."
    return llm(prompt, system=system, model="opus", max_tokens=8000)
