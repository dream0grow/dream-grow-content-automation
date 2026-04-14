"""콘텐츠 자동 사전 검수기 - 규칙 위반 자동 탐지 + 수정

05 리뷰/대기/ 파일을 스캔하여:
1. 규칙 위반 탐지 (이모지, 가짜 통계, 마무리 문구 등)
2. 자동 수정 가능한 것은 즉시 수정
3. 사람 확인 필요한 것은 frontmatter에 검수메모 추가
4. 전체 통과하면 검수상태: 통과 표시

사용법:
  python3 content_reviewer.py              # 전체 리뷰대기 검수
  python3 content_reviewer.py --file "파일" # 단일 파일 검수
  python3 content_reviewer.py --fix        # 자동 수정까지 실행
"""
import os
import re
import sys
from datetime import datetime

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/대기")
BACKUP_DIR = "/Users/lhg/Library/CloudStorage/Dropbox/1.한결/나/ㄱ.클로드코드_드림그로우/content-automation/.ai_drafts"

# 한글 손실 방지 가드: 자동 수정 후 한글 비율이 원본의 절반 미만이면 중단
HANGUL_RE = re.compile(r'[가-힣]')


def _hangul_count(text: str) -> int:
    return len(HANGUL_RE.findall(text))


def _safe_substitute(pattern, replacement, text: str, label: str = "") -> str:
    """pattern.sub을 실행하되 한글 손실 감지 시 원본을 그대로 반환.

    이전 버전의 이모지 정규식 버그처럼 패턴이 잘못 지정되면 한글이 대량으로
    사라질 수 있다. 치환 직후 한글 개수를 비교해 원본의 절반 미만이 되면
    해당 치환은 무효화한다.
    """
    new_text = pattern.sub(replacement, text)
    if new_text == text:
        return text
    orig_kor = _hangul_count(text)
    new_kor = _hangul_count(new_text)
    if orig_kor >= 10 and new_kor < orig_kor * 0.8:
        print(
            f"  [REVERT] {label or 'substitution'}: 한글 {orig_kor}->{new_kor}, "
            f"치환 무효화 (패턴 오작동 의심)"
        )
        return text
    return new_text


def _safe_write(filepath: str, original: str, new_content: str,
                original_body: str = "", new_body: str = "") -> bool:
    """원본 백업 후 안전하게 덮어쓴다.

    body 기준으로 한글 손실을 검증한다. frontmatter에 한글이 남아 있어 전체
    비율이 흐려지는 문제를 피하기 위함. body 인자가 비면 전체 content로 폴백.
    """
    check_before = original_body or original
    check_after = new_body or new_content
    orig_kor = _hangul_count(check_before)
    new_kor = _hangul_count(check_after)
    if orig_kor >= 10 and new_kor < orig_kor * 0.8:
        print(
            f"  [ABORT] {os.path.basename(filepath)}: 본문 한글 "
            f"{orig_kor}->{new_kor}, 자동수정 중단"
        )
        return False
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(filepath))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"{stem}_{ts}{ext}")
    with open(backup_path, "w", encoding="utf-8") as bf:
        bf.write(original)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _split_frontmatter(content: str) -> tuple:
    """파일을 (frontmatter_block, body)로 분리. frontmatter 없으면 ('', content)."""
    if not content.startswith("---"):
        return "", content
    end_idx = content.find("\n---", 3)
    if end_idx < 0:
        return "", content
    fm_end = end_idx + len("\n---")
    # frontmatter 블록 뒤 개행 1개까지 포함
    if fm_end < len(content) and content[fm_end] == "\n":
        fm_end += 1
    return content[:fm_end], content[fm_end:]

# 이모지 감지 (실제 이모지만, 한글/기호 제외)
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"  # 이모티콘 (웃는 얼굴 등)
    "\U0001F300-\U0001F5FF"  # 기호 & 픽토그래프
    "\U0001F680-\U0001F6FF"  # 교통 & 지도
    "\U0001F1E0-\U0001F1FF"  # 국기
    "\U0001F900-\U0001F9FF"  # 보충 이모지
    "\U0001FA00-\U0001FAFF"  # 확장 이모지
    "]+", flags=re.UNICODE
)

# 가짜 통계 패턴 (출처 없는 %)
FAKE_STAT_PATTERN = re.compile(r'\d{1,3}%')

# 금지 마무리 패턴
BAD_ENDINGS = [
    "과학적으로 건강하게 성장하는 법을 돕습니다",
    "돕습니다.",
    "도움이 되길 바랍니다",
]

# 필수 마무리
REQUIRED_ENDING = "아이와 부모의 꿈을 키웁니다."
BRAND_SIGNATURE = "-Dream_Grow-"

# 마크다운 정리 패턴
MD_CLEANUP_PATTERNS = [
    (re.compile(r'\[(\d+)/(\d+)\]\s*'), ''),           # [1/7] 제거
    (re.compile(r'\[Hook\]\s*', re.IGNORECASE), ''),    # [Hook] 제거
    (re.compile(r'\[CTA\]\s*', re.IGNORECASE), ''),     # [CTA] 제거
    (re.compile(r'\[마무리\]\s*'), ''),                   # [마무리] 제거
    (re.compile(r'\*\*\[?\d+/\d+\]?\*\*\s*'), ''),     # **[1/7]** 제거
]


class ReviewResult:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.issues = []       # (severity, category, description, line_num)
        self.auto_fixes = []   # (description, before, after)
        self.passed = False

    def add_issue(self, severity: str, category: str, desc: str, line: int = 0):
        self.issues.append((severity, category, desc, line))

    def add_fix(self, desc: str, before: str = "", after: str = ""):
        self.auto_fixes.append((desc, before, after))

    def summary(self) -> str:
        if self.passed:
            return f"  통과: {self.filename}"
        lines = [f"  {self.filename}: {len(self.issues)}개 이슈"]
        for sev, cat, desc, line in self.issues:
            loc = f" (L{line})" if line else ""
            lines.append(f"    [{sev}] {cat}: {desc}{loc}")
        if self.auto_fixes:
            lines.append(f"    자동 수정: {len(self.auto_fixes)}건")
        return "\n".join(lines)


def review_file(filepath: str, auto_fix: bool = False) -> ReviewResult:
    """단일 파일을 검수합니다."""
    result = ReviewResult(filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    original = content

    # frontmatter와 body 분리: 모든 치환은 body에만 적용한다.
    frontmatter, body = _split_frontmatter(content)
    original_body = body
    body_lines = body.split("\n")

    # 1. 이모지 검사 + 자동 제거 (body에만, 한글 손실 가드 포함)
    emojis = EMOJI_PATTERN.findall(body)
    if emojis:
        result.add_issue("ERROR", "이모지", f"이모지 {len(emojis)}개 발견: {' '.join(emojis[:5])}")
        if auto_fix:
            body = _safe_substitute(EMOJI_PATTERN, "", body, "이모지 제거")
            result.add_fix(f"이모지 {len(emojis)}개 제거")

    # 2. 가짜 통계 검사
    for i, line in enumerate(body_lines, 1):
        if FAKE_STAT_PATTERN.search(line):
            has_source = any(kw in body for kw in ["연구", "논문", "조사", "발표", "학회", "대학교"])
            if not has_source:
                result.add_issue("WARN", "가짜통계", f"출처 없는 수치: {line.strip()[:50]}", i)

    # 3. 마무리 문구 검사
    last_200 = body[-200:] if len(body) > 200 else body
    for bad in BAD_ENDINGS:
        if bad in last_200:
            result.add_issue("ERROR", "마무리", f"금지 마무리 발견: '{bad}'")

    if REQUIRED_ENDING not in body and BRAND_SIGNATURE not in body:
        result.add_issue("WARN", "마무리", "브랜드 서명 누락 (아이와 부모의 꿈을 키웁니다. -Dream_Grow-)")

    # 4. 마크다운 정리 (body에만, 한글 손실 가드 포함)
    for pattern, replacement in MD_CLEANUP_PATTERNS:
        matches = pattern.findall(body)
        if matches:
            if auto_fix:
                body = _safe_substitute(pattern, replacement, body, "마크다운 정리")
                result.add_fix(f"마크다운 패턴 제거 ({len(matches)}건)")
            else:
                result.add_issue("INFO", "마크다운", f"불필요한 마크다운 패턴 {len(matches)}개")

    # 5. 해시태그 검사 (스레드)
    if "채널: thread" in frontmatter or "스레드_" in result.filename:
        if "#" not in body[-300:]:
            result.add_issue("INFO", "해시태그", "해시태그 누락 (스레드 끝에 5~7개 권장)")

    # 6. 글자 수 검사
    body_clean = re.sub(r'\s+', '', body)
    if "스레드" in result.filename and len(body_clean) < 400:
        result.add_issue("WARN", "길이", f"스레드 본문 {len(body_clean)}자 (최소 500자 권장)")
    if "릴스" in result.filename and len(body_clean) > 500:
        result.add_issue("INFO", "길이", f"릴스 본문 {len(body_clean)}자 (200~400자 권장)")

    # 7. frontmatter 필수 필드 검사
    for field in ["주제", "카테고리", "상태", "생성일"]:
        if f"{field}:" not in frontmatter:
            result.add_issue("WARN", "속성", f"frontmatter 누락: {field}")

    # 자동 수정 적용: frontmatter는 검수상태 필드만 조작, body는 치환된 결과로 재조합
    new_frontmatter = frontmatter
    new_content = frontmatter + body
    body_changed = body != original_body
    if auto_fix and body_changed:
        if "검수상태:" not in new_frontmatter:
            new_frontmatter = new_frontmatter.replace(
                "발행시간:", "검수상태: 자동수정완료\n발행시간:", 1
            )
        new_content = new_frontmatter + body
        if not _safe_write(filepath, original, new_content,
                           original_body=original_body, new_body=body):
            return result

    # 통과 판정
    errors = [i for i in result.issues if i[0] == "ERROR"]
    if not errors:
        result.passed = True
        if auto_fix and "검수상태:" not in new_frontmatter:
            new_frontmatter = new_frontmatter.replace(
                "발행시간:", "검수상태: 통과\n발행시간:", 1
            )
            new_content = new_frontmatter + body
            _safe_write(filepath, original, new_content,
                        original_body=original_body, new_body=body)

    return result


def review_all(auto_fix: bool = False) -> list:
    """리뷰대기 전체 파일을 검수합니다."""
    results = []
    if not os.path.isdir(REVIEW_DIR):
        print("05 리뷰/대기/ 폴더가 없습니다.")
        return results

    files = [f for f in os.listdir(REVIEW_DIR) if f.endswith(".md")]
    print(f"[{datetime.now().strftime('%H:%M')}] 검수 시작: {len(files)}개 파일")
    if auto_fix:
        print("  모드: 자동 수정 활성화")
    print()

    passed = 0
    for fname in sorted(files):
        filepath = os.path.join(REVIEW_DIR, fname)
        result = review_file(filepath, auto_fix=auto_fix)
        results.append(result)
        if result.passed:
            passed += 1
        if result.issues:
            print(result.summary())

    print(f"\n--- 검수 결과 ---")
    print(f"  전체: {len(results)}개")
    print(f"  통과: {passed}개")
    print(f"  이슈: {len(results) - passed}개")
    if auto_fix:
        total_fixes = sum(len(r.auto_fixes) for r in results)
        print(f"  자동 수정: {total_fixes}건")

    return results


def main():
    auto_fix = "--fix" in sys.argv

    if "--file" in sys.argv:
        idx = sys.argv.index("--file")
        if idx + 1 < len(sys.argv):
            filepath = sys.argv[idx + 1]
            if not os.path.exists(filepath):
                filepath = os.path.join(REVIEW_DIR, filepath)
            if os.path.exists(filepath):
                result = review_file(filepath, auto_fix=auto_fix)
                print(result.summary())
            else:
                print(f"파일 없음: {sys.argv[idx + 1]}")
        return

    review_all(auto_fix=auto_fix)


if __name__ == "__main__":
    main()
