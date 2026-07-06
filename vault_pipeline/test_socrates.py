"""socrates 새벽 질문 잡 테스트 (LLM mock)"""
import pytest

from orchestrator import llm
from vault_pipeline import socrates


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    kw = tmp_path / "제텔카스텐/2. 키워드"
    kw.mkdir(parents=True)
    (kw / "K_ai - 오답 친화 교실.md").write_text(
        "---\ntitle: 오답 친화 교실\nauthor: AI\n---\n\n"
        "**What**: 오답을 배움의 재료로 쓰는 교실 문화\n", encoding="utf-8")
    monkeypatch.setattr(llm, "call_json", lambda *a, **k: {
        "질문": ["오답이 항상 배움의 재료라면, 정답은 무엇을 가르치는가?",
               "교실 한 칸에서 통하는 이 문화가 평가 제도 전체에서는 왜 무너지는가?",
               "이것은 사실 실패에 관한 문제인가, 안전에 관한 문제인가?"]})
    return tmp_path


def test_socrates_creates_dialogue(vault):
    socrates.main()
    files = list((vault / "_system/dialogues").glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "재료: K_ai - 오답 친화 교실" in text
    assert "직관" in text and "나의 답" in text
    assert "정답은 무엇을 가르치는가" in text

    # 같은 날 재실행 시 중복 생성 없음
    socrates.main()
    assert len(list((vault / "_system/dialogues").glob("*.md"))) == 1


def test_socrates_skips_used_material(vault):
    socrates.main()
    # 재료가 하나뿐이고 이미 사용됨 → 다음 날 실행이면 재료 없음 판단
    dialogue = next((vault / "_system/dialogues").glob("*.md"))
    dialogue.rename(dialogue.with_name("2000-01-01.md"))  # 과거 날짜로 위장
    assert socrates.pick_material() is None
