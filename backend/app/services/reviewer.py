"""콘텐츠 규칙 검수기 - 레거시 content_reviewer.py 포팅 (문자열/DB 기반)

규칙: 이모지 금지, 출처 없는 % 수치 경고, 금지 마무리 문구, 브랜드 서명,
마크다운 잔여 패턴, 포스트별 글자 수 (스레드 500 하드 / 280 스타일).
자동 수정은 한글 손실 가드(_safe_substitute)로 보호한다.
"""
import re

from app.core.constants import THREADS_HARD_LIMIT, THREADS_STYLE_LIMIT
from app.services.splitter import split_posts

HANGUL_RE = re.compile(r"[가-힣]")

# 이모지 감지 (실제 이모지만, 한글/기호 제외)
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"  # 이모티콘
    "\U0001F300-\U0001F5FF"  # 기호 & 픽토그래프
    "\U0001F680-\U0001F6FF"  # 교통 & 지도
    "\U0001F1E0-\U0001F1FF"  # 국기
    "\U0001F900-\U0001F9FF"  # 보충 이모지
    "\U0001FA00-\U0001FAFF"  # 확장 이모지
    "]+",
    flags=re.UNICODE,
)

FAKE_STAT_PATTERN = re.compile(r"\d{1,3}%")
SOURCE_KEYWORDS = ["연구", "논문", "조사", "발표", "학회", "대학교"]

BAD_ENDINGS = [
    "과학적으로 건강하게 성장하는 법을 돕습니다",
    "돕습니다.",
    "도움이 되길 바랍니다",
]

REQUIRED_ENDING = "아이와 부모의 꿈을 키웁니다."
BRAND_SIGNATURE = "-Dream_Grow-"

MD_CLEANUP_PATTERNS = [
    (re.compile(r"\[Hook\]\s*", re.IGNORECASE), ""),
    (re.compile(r"\[CTA\]\s*", re.IGNORECASE), ""),
    (re.compile(r"\[마무리\]\s*"), ""),
    (re.compile(r"\*\*\[?\d+/\d+\]?\*\*\s*"), ""),
]


def _hangul_count(text: str) -> int:
    return len(HANGUL_RE.findall(text))


def _safe_substitute(pattern: re.Pattern, replacement: str, text: str) -> tuple[str, bool]:
    """치환 후 한글이 원본의 80% 미만으로 줄면 무효화 (패턴 오작동 방지)."""
    new_text = pattern.sub(replacement, text)
    if new_text == text:
        return text, False
    orig_kor = _hangul_count(text)
    new_kor = _hangul_count(new_text)
    if orig_kor >= 10 and new_kor < orig_kor * 0.8:
        return text, False
    return new_text, True


def review(body: str, content_type: str) -> dict:
    """본문 검수. ReviewResult dict 반환:
    {passed, issues: [{severity, category, message, post_index?}], auto_fixable}
    """
    issues: list[dict] = []
    auto_fixable = False

    # 1. 이모지
    emojis = EMOJI_PATTERN.findall(body)
    if emojis:
        issues.append({
            "severity": "ERROR", "category": "이모지",
            "message": f"이모지 {len(emojis)}개 발견: {' '.join(emojis[:5])}",
        })
        auto_fixable = True

    # 2. 가짜 통계 (출처 없는 %)
    has_source = any(kw in body for kw in SOURCE_KEYWORDS)
    if not has_source:
        for line in body.split("\n"):
            if FAKE_STAT_PATTERN.search(line):
                issues.append({
                    "severity": "WARN", "category": "가짜통계",
                    "message": f"출처 없는 수치: {line.strip()[:50]}",
                })

    # 3. 마무리 문구
    last_200 = body[-200:] if len(body) > 200 else body
    for bad in BAD_ENDINGS:
        if bad in last_200:
            issues.append({
                "severity": "ERROR", "category": "마무리",
                "message": f"금지 마무리 발견: '{bad}'",
            })
    if REQUIRED_ENDING not in body and BRAND_SIGNATURE not in body:
        issues.append({
            "severity": "WARN", "category": "마무리",
            "message": f"브랜드 서명 누락 ({REQUIRED_ENDING} {BRAND_SIGNATURE})",
        })

    # 4. 마크다운 잔여 패턴
    md_count = sum(len(p.findall(body)) for p, _ in MD_CLEANUP_PATTERNS)
    if md_count:
        issues.append({
            "severity": "INFO", "category": "마크다운",
            "message": f"불필요한 마크다운 패턴 {md_count}개",
        })
        auto_fixable = True

    # 5. 글자 수
    if content_type == "thread":
        posts = split_posts(body)
        for i, post in enumerate(posts):
            if len(post) > THREADS_HARD_LIMIT:
                issues.append({
                    "severity": "ERROR", "category": "길이",
                    "message": f"{i + 1}번 글 {len(post)}자 - Threads 제한 {THREADS_HARD_LIMIT}자 초과",
                    "post_index": i,
                })
            elif len(post) > THREADS_STYLE_LIMIT:
                issues.append({
                    "severity": "WARN", "category": "길이",
                    "message": f"{i + 1}번 글 {len(post)}자 - 권장 {THREADS_STYLE_LIMIT}자 초과",
                    "post_index": i,
                })
        body_clean = re.sub(r"\s+", "", body)
        if len(body_clean) < 400:
            issues.append({
                "severity": "WARN", "category": "길이",
                "message": f"스레드 본문 {len(body_clean)}자 (최소 500자 권장)",
            })
    elif content_type == "reels":
        body_clean = re.sub(r"\s+", "", body)
        if len(body_clean) > 1500:
            issues.append({
                "severity": "INFO", "category": "길이",
                "message": f"릴스 본문 {len(body_clean)}자 (대본+B-roll 포함 적정 분량 확인)",
            })

    errors = [i for i in issues if i["severity"] == "ERROR"]
    return {"passed": not errors, "issues": issues, "auto_fixable": auto_fixable}


def apply_fixes(body: str) -> tuple[str, list[str]]:
    """안전한 자동 수정 적용. (수정된 본문, 수정 내역) 반환."""
    fixes: list[str] = []

    emojis = EMOJI_PATTERN.findall(body)
    if emojis:
        body, changed = _safe_substitute(EMOJI_PATTERN, "", body)
        if changed:
            fixes.append(f"이모지 {len(emojis)}개 제거")

    for pattern, replacement in MD_CLEANUP_PATTERNS:
        matches = pattern.findall(body)
        if matches:
            body, changed = _safe_substitute(pattern, replacement, body)
            if changed:
                fixes.append(f"마크다운 패턴 제거 ({len(matches)}건)")

    return body, fixes
