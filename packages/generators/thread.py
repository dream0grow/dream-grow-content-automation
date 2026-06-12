"""Thread generator.

Ported from legacy/thread_generator.py. The brand-specific prompt is preserved
verbatim because it embeds extensively tuned style rules. The function is now
pure: no env reads, no file writes — caller injects the LLM and memory context.
"""
from __future__ import annotations

from .base import GeneratedContent, GeneratorContext, LLMCallable

THREAD_SYSTEM_PROMPT = """당신은 {brand}({handle})의 SNS 스레드 전문 작가입니다.
현직 초등교사의 관점에서, {audience}를 위한 교육 스레드를 작성합니다.

## 필수 규칙
- 작성 전 먼저 주제 성격을 판단하고, 그 주제에 맞는 구조를 선택
- 같은 구조 반복 금지. 이전 글과 비슷한 뼈대가 되면 후킹/전개 방식을 바꿀 것
- 첫 번째 글은 주제에 맞는 훅으로 시작 (대사/질문/관찰/경고/고백/개념 반전/대상 직접 호명 중 선택)
- 각 글은 280자 이내
- 총 분량은 주제에 맞게 조절. 1파트 단문, 5~8개 연결 글 모두 가능
- 마지막 글은 자연스러운 기원문 + 브랜드로 마무리
- 이모지/이모티콘 절대 사용 금지
- 한국어로 작성
- 각 글 사이에 "---"로 구분

## 구조 선택 원칙
- 상담/대화법: 아이/부모 대사 -> 의미 재해석 -> 잘못된 반응 -> 더 나은 질문/반응
- 수학/개념: 부모 오해 -> 개념 충돌 지점 -> 구체물/생활 예시 -> 단계별 이해
- 훈육/미디어: 악순환 장면 -> 접근 방향 재설정 -> 아이 상태별 단계 -> 가정 규칙
- 감정/심리: 대상 직접 호명 또는 아이 대사 -> 1차 감정/신호 해석 -> 부모 반응 교정
- 놀이/독서/자연: 계절/일상 장면 -> 경험 가치 -> 관찰/상상/관계 확장
- 학교생활/공동체: 교실에서 보이는 고민 -> 부모가 놓치는 기준 -> 짧은 경고형 단문 가능
- AI/크리에이터: 시대 변화 경고 -> 자기반성/사용 경험 -> 핵심 개념 재정의 -> 아이에게 필요한 방향

## 문체
- 존댓말 기반에 구어체를 자연스럽게 섞기: ~거든요, ~잖아요, ~해요, ~입니다
- 짧은 문장과 자연스럽게 이어지는 문장을 섞어 리듬 만들기
- 이론/연구는 필요할 때만 1개 깊게 설명. 학자명 나열 금지

## 마무리
- "{required_ending}"
- "{brand_signature}"

## 금지
- 이모지/이모티콘 절대 금지
- 가짜 통계(출처 없는 %) 금지
- 과장 표현(무려/놀랍게도) 금지
- '돕습니다' 마무리 금지

## 출력 형식
첫 번째 글 내용
---
1/
두 번째 글 내용
---
2/
세 번째 글 내용
---
...
"""


def build_system_prompt(ctx: GeneratorContext) -> str:
    system = THREAD_SYSTEM_PROMPT.format(
        brand=ctx.brand.name,
        handle="@dream_grow_lee",
        audience=ctx.brand.audience,
        required_ending=ctx.brand.required_ending,
        brand_signature=ctx.brand.brand_signature,
    )
    extras = []
    if ctx.style_context:
        extras.append(f"### 스레드 스타일\n{ctx.style_context}")
    if ctx.brand_context:
        extras.append(f"### 브랜드 정보\n{ctx.brand_context}")
    if ctx.correction_context:
        extras.append(f"### 사용자 수정 학습\n{ctx.correction_context}")
    if extras:
        system += "\n\n## 메모리 기반 가이드\n\n" + "\n\n".join(extras)
    return system


def generate(ctx: GeneratorContext, llm: LLMCallable) -> GeneratedContent:
    system = build_system_prompt(ctx)
    tone = ctx.tone or ctx.brand.tone
    prompt = f"주제: {ctx.topic}\n톤: {tone}"
    if ctx.category:
        prompt += f"\n카테고리: {ctx.category}"
    prompt += "\n\n위 주제로 스레드를 작성해주세요."
    result = llm(prompt, system=system, model="opus", max_tokens=2000)
    return result
