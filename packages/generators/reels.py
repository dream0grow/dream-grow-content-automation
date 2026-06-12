from __future__ import annotations

from .base import GeneratedContent, GeneratorContext, LLMCallable

REELS_SYSTEM = """당신은 {brand}의 인스타그램 릴스 스크립트 작가입니다.
35~45초 분량의 한국어 영상 스크립트를 작성합니다.

## 구조
- [Hook] 0~3초: 한 문장으로 부모가 멈추게 만드는 후킹
- [Pain] 3~10초: 흔한 잘못된 반응 장면
- [Insight] 10~25초: 핵심 통찰 1개
- [Tactic] 25~38초: 오늘 바로 적용할 한 가지 행동
- [CTA] 38~45초: 댓글 유도 또는 리드마그넷 안내

## 추가 출력
- B-roll: 각 구간별 추천 화면 (장면, 표정, 자막 키워드)
- 자막 키 카피: 최대 6줄
- 이모지 금지, 출처 없는 통계 금지
"""


def generate(ctx: GeneratorContext, llm: LLMCallable) -> GeneratedContent:
    system = REELS_SYSTEM.format(brand=ctx.brand.name)
    if ctx.style_context:
        system += f"\n\n## 스타일 메모리\n{ctx.style_context}"
    refs = "\n\n".join(f"### 원본 스레드\n{r}" for r in ctx.reference_bodies)
    prompt = f"주제: {ctx.topic}\n카테고리: {ctx.category or ''}\n\n{refs}"
    return llm(prompt, system=system, model="sonnet", max_tokens=2000)
