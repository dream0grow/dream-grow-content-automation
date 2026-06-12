from app.services.reviewer import EMOJI_PATTERN, _safe_substitute, apply_fixes, review

BRAND = "아이와 부모의 꿈을 키웁니다. -Dream_Grow-"


def _ok_thread() -> str:
    return (
        "교실에서 매일 보는 장면이 있습니다. 아이들의 공부 이야기를 해보려 합니다.\n---\n"
        "1/\n아이가 노력을 안 하는 게 아니라 방법을 모르는 경우가 많습니다. "
        "교실에서 보면 시작점을 못 찾는 아이가 대부분이거든요.\n---\n"
        "2/\n어디서 막혔는지 묻는 질문 하나가 공부 습관의 시작이 됩니다. "
        "오늘 저녁 한 번 시도해 보세요.\n\n"
        f"아이가 건강하게 자라길 바랍니다.\n{BRAND}"
    )


def test_clean_thread_passes():
    result = review(_ok_thread(), "thread")
    assert result["passed"]


def test_emoji_detected_and_fixed():
    body = _ok_thread() + " 화이팅 \U0001F600"
    result = review(body, "thread")
    assert any(i["category"] == "이모지" and i["severity"] == "ERROR" for i in result["issues"])
    assert result["auto_fixable"]

    fixed, fixes = apply_fixes(body)
    assert "\U0001F600" not in fixed
    assert any("이모지" in f for f in fixes)
    assert review(fixed, "thread")["passed"]


def test_hangul_loss_guard():
    import re
    # 한글을 전부 지워버리는 잘못된 패턴 - 가드가 무효화해야 함
    bad_pattern = re.compile(r"[가-힣]+")
    text = "한글이 많은 본문입니다. 한글이 사라지면 안 됩니다. 가나다라마바사."
    result, changed = _safe_substitute(bad_pattern, "", text)
    assert result == text
    assert not changed


def test_fake_stat_warning():
    body = _ok_thread().replace("아이들의 공부 이야기", "아이들의 80%가 겪는 이야기")
    result = review(body, "thread")
    assert any(i["category"] == "가짜통계" for i in result["issues"])

    # 출처 키워드가 있으면 경고 없음
    body_with_source = body.replace("교실에서 매일", "서울대학교 연구에 따르면 교실에서 매일")
    result2 = review(body_with_source, "thread")
    assert not any(i["category"] == "가짜통계" for i in result2["issues"])


def test_bad_ending_error():
    body = _ok_thread().replace(
        "아이가 건강하게 자라길 바랍니다.", "과학적으로 건강하게 성장하는 법을 돕습니다"
    )
    result = review(body, "thread")
    assert any(i["category"] == "마무리" and i["severity"] == "ERROR" for i in result["issues"])
    assert not result["passed"]


def test_missing_brand_signature_warn():
    body = _ok_thread().replace(BRAND, "").replace("아이가 건강하게 자라길 바랍니다.", "끝입니다.")
    result = review(body, "thread")
    assert any(i["category"] == "마무리" and i["severity"] == "WARN" for i in result["issues"])


def test_post_over_500_error():
    long_post = "가" * 501
    body = f"{_ok_thread()}\n---\n{long_post}"
    result = review(body, "thread")
    over = [i for i in result["issues"] if i["category"] == "길이" and i["severity"] == "ERROR"]
    assert over
    assert not result["passed"]


def test_post_over_280_warn():
    long_post = "가" * 300
    body = f"{_ok_thread()}\n---\n{long_post}"
    result = review(body, "thread")
    warns = [i for i in result["issues"] if i["category"] == "길이" and i["severity"] == "WARN"]
    assert warns
    assert result["passed"]  # WARN만으로는 통과
