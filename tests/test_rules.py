from packages.shared.rules import autofix, validate
from packages.shared.enums import IssueSeverity


def test_emoji_triggers_error():
    body = "안녕하세요 😀 오늘은 좋은 날입니다."
    result = validate(body, channel="thread")
    assert not result.passed
    assert any(i.severity == IssueSeverity.ERROR and i.category == "이모지"
               for i in result.issues)


def test_banned_ending_triggers_error():
    body = ("아이가 건강하게 자라길 바랍니다.\n"
            "오늘도 행복한 하루 보내세요. 돕습니다.")
    result = validate(body, channel="thread")
    assert any(i.category == "마무리" for i in result.issues)


def test_brand_signature_pass():
    body = "한참 길고도 길어요. " * 60 + "\n아이와 부모의 꿈을 키웁니다. -Dream_Grow-"
    result = validate(body, channel="thread")
    assert result.passed


def test_autofix_removes_emojis_and_markers():
    body = "😀 안녕하세요\n[1/7] 본문 시작 [Hook] 강한 후킹\n끝"
    new_body, applied = autofix(body)
    assert "😀" not in new_body
    assert "[1/7]" not in new_body
    assert "[Hook]" not in new_body
    assert applied  # at least one fix
