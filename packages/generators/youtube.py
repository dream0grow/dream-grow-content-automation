from __future__ import annotations

from .base import GeneratedContent, GeneratorContext, LLMCallable

YOUTUBE_SYSTEM = """당신은 {brand} 유튜브 채널의 8~15분 분량 스크립트 작가입니다.
시청자는 {audience}이며, 다음 구조를 따릅니다.

1. Cold Open (15초): 강한 후킹 장면 묘사 + 첫 문장
2. Intro (45초): 오늘 다룰 질문 + 시청자가 얻을 것
3. Body 1 (3분): 개념 정의
4. Body 2 (3분): 부모가 자주 빠지는 함정 + 사례
5. Body 3 (3분): 적용 가능한 3단계 방법
6. Outro (90초): 요약 + 채널 구독 유도 + 다음 영상 예고

## 추가 출력
- 썸네일 카피 후보 3개
- 영상 설명란 (검색 키워드 포함)
"""


def generate(ctx: GeneratorContext, llm: LLMCallable) -> GeneratedContent:
    system = YOUTUBE_SYSTEM.format(brand=ctx.brand.name, audience=ctx.brand.audience)
    prompt = f"주제: {ctx.topic}\n카테고리: {ctx.category or ''}"
    return llm(prompt, system=system, model="opus", max_tokens=6000)
