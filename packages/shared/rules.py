"""Brand rule definitions ported from legacy content_reviewer.py.

Pure data + a single validate() function returning structured Issues.
No filesystem, no env reads, no autofix side effects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .enums import IssueSeverity

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)
FAKE_STAT_PATTERN = re.compile(r"\d{1,3}%")

DEFAULT_BANNED_ENDINGS = (
    "과학적으로 건강하게 성장하는 법을 돕습니다",
    "돕습니다.",
    "도움이 되길 바랍니다",
)
DEFAULT_REQUIRED_ENDING = "아이와 부모의 꿈을 키웁니다."
DEFAULT_BRAND_SIGNATURE = "-Dream_Grow-"

SOURCE_KEYWORDS = ("연구", "논문", "조사", "발표", "학회", "대학교")

MD_NOISE_PATTERNS = (
    (re.compile(r"\[(\d+)/(\d+)\]\s*"), ""),
    (re.compile(r"\[Hook\]\s*", re.IGNORECASE), ""),
    (re.compile(r"\[CTA\]\s*", re.IGNORECASE), ""),
    (re.compile(r"\[마무리\]\s*"), ""),
    (re.compile(r"\*\*\[?\d+/\d+\]?\*\*\s*"), ""),
)


@dataclass
class Issue:
    severity: IssueSeverity
    category: str
    message: str
    line: int = 0


@dataclass
class ValidationResult:
    passed: bool
    issues: list[Issue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)


@dataclass
class BrandRules:
    banned_phrases: tuple[str, ...] = DEFAULT_BANNED_ENDINGS
    required_ending: str = DEFAULT_REQUIRED_ENDING
    brand_signature: str = DEFAULT_BRAND_SIGNATURE


def validate(body: str, channel: str | None = None, rules: BrandRules | None = None) -> ValidationResult:
    """Run all brand rule checks against a markdown body."""
    rules = rules or BrandRules()
    issues: list[Issue] = []

    # 1. emoji ban
    emojis = EMOJI_PATTERN.findall(body)
    if emojis:
        sample = " ".join(emojis[:5])
        issues.append(Issue(IssueSeverity.ERROR, "이모지", f"이모지 {len(emojis)}개 발견: {sample}"))

    # 2. fake statistics
    has_source = any(kw in body for kw in SOURCE_KEYWORDS)
    if not has_source:
        for i, line in enumerate(body.split("\n"), 1):
            if FAKE_STAT_PATTERN.search(line):
                issues.append(Issue(IssueSeverity.WARN, "가짜통계",
                                    f"출처 없는 수치: {line.strip()[:50]}", i))

    # 3. banned closing phrases
    tail = body[-300:] if len(body) > 300 else body
    for bad in rules.banned_phrases:
        if bad in tail:
            issues.append(Issue(IssueSeverity.ERROR, "마무리", f"금지 마무리 발견: '{bad}'"))

    # 4. required brand signature
    if (rules.required_ending and rules.required_ending not in body
            and rules.brand_signature not in body):
        issues.append(Issue(IssueSeverity.WARN, "마무리",
                            f"브랜드 서명 누락 ({rules.required_ending} {rules.brand_signature})"))

    # 5. markdown noise
    for pattern, _ in MD_NOISE_PATTERNS:
        matches = pattern.findall(body)
        if matches:
            issues.append(Issue(IssueSeverity.INFO, "마크다운",
                                f"불필요한 마크다운 패턴 {len(matches)}개"))

    # 6. length heuristics per channel
    body_clean = re.sub(r"\s+", "", body)
    if channel == "thread" and len(body_clean) < 400:
        issues.append(Issue(IssueSeverity.WARN, "길이",
                            f"스레드 본문 {len(body_clean)}자 (최소 500자 권장)"))
    if channel == "reels" and len(body_clean) > 500:
        issues.append(Issue(IssueSeverity.INFO, "길이",
                            f"릴스 본문 {len(body_clean)}자 (200~400자 권장)"))

    passed = not any(i.severity == IssueSeverity.ERROR for i in issues)
    return ValidationResult(passed=passed, issues=issues)


def autofix(body: str) -> tuple[str, list[str]]:
    """Apply safe autofixes (emoji removal + markdown noise stripping).

    Returns (new_body, applied_descriptions).
    """
    applied: list[str] = []
    new_body = body
    emoji_count = len(EMOJI_PATTERN.findall(new_body))
    if emoji_count:
        new_body = EMOJI_PATTERN.sub("", new_body)
        applied.append(f"이모지 {emoji_count}개 제거")
    for pattern, repl in MD_NOISE_PATTERNS:
        matches = pattern.findall(new_body)
        if matches:
            new_body = pattern.sub(repl, new_body)
            applied.append(f"마크다운 패턴 {len(matches)}개 제거")
    return new_body, applied
