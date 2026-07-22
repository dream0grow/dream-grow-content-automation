"""벤치마킹 소스 인제스트(source_ingest) 단위테스트.

실행: python3 -m pytest orchestrator/test_source_ingest.py -q
"""
import pytest

from orchestrator import run, source_ingest
from orchestrator.test_run import FakeState


NAVER_HTML = """<html><head>
<title>페이지 타이틀</title>
<meta property="og:title" content="초등 문해력 논란, 진짜 원인은 따로 있다" />
</head><body>
<script>var x = 1;</script>
<article id="dic_area" class="go_trans">
  기사 첫 문단입니다. 초등학생 문해력 저하가 화제다.<br/>
  전문가는 &quot;독서 시간이 줄었다&quot;고 말했다.
  <p>""" + "본문 문장입니다. " * 30 + """</p>
</article>
</body></html>"""


# ---------- HTML 추출 ----------

def test_extract_naver_article():
    title = source_ingest._extract_title(NAVER_HTML)
    body = source_ingest._extract_body(NAVER_HTML)
    assert title == "초등 문해력 논란, 진짜 원인은 따로 있다"
    assert "기사 첫 문단입니다" in body
    assert '"독서 시간이 줄었다"' in body   # 엔티티 복원
    assert "var x" not in body              # script 제거
    assert "<p>" not in body                # 태그 제거


def test_extract_generic_article_and_fallback():
    generic = ("<html><body><nav>메뉴</nav><article>"
               + "블로그 본문 문장. " * 30 + "</article></body></html>")
    assert "블로그 본문 문장" in source_ingest._extract_body(generic)
    # article 후보가 없으면 body 전체로 폴백
    bare = "<html><body><div>" + "짧은 글. " * 40 + "</div></body></html>"
    assert "짧은 글" in source_ingest._extract_body(bare)


# ---------- ingest ----------

class IngestState(FakeState):
    """append/read 섹션까지 기록하는 가짜 저장소."""

    def __init__(self, sections=None):
        super().__init__(sections=sections)
        self.appended = []  # (page_id, heading, body)

    def append_section(self, page_id, heading, body):
        self.appended.append((page_id, heading, body))
        self._sections[(page_id, heading)] = body

    append_formatted_section = append_section


ANALYSIS = {
    "source_title": "초등 문해력 논란", "source_type": "기사",
    "summary": "요약", "suggested_topic": "책 읽어도 문해력 걱정되는 아이, 무엇부터 볼까",
    "key_facts": ["독서 시간 감소 (경향신문)"], "hook_pattern": "통계 제시",
    "structure_pattern": "사례→인용", "tone": "차분", "dreamgrow_angles": ["가정 독서"],
    "caution": ["불안 조장 주의"],
}


def test_ingest_without_source_returns_false():
    st = IngestState()
    source_ingest.store = st
    card = {"page_id": "p1", "topic": "일반 주제", "source_url": "", "audience": ""}
    assert source_ingest.ingest(card) is False
    assert not st.appended


def test_ingest_fetches_url_analyzes_and_sets_topic(monkeypatch):
    st = IngestState()
    source_ingest.store = st
    monkeypatch.setattr(source_ingest, "fetch_url",
                        lambda url: ("기사 제목", "기사 본문 " * 100))
    monkeypatch.setattr(source_ingest.llm, "call_json", lambda *a, **k: dict(ANALYSIS))
    card = {"page_id": "p1", "topic": "(소스) 벤치마킹 발제 대기",
            "source_url": "https://example.com/a", "audience": "학부모"}
    assert source_ingest.ingest(card) is True
    headings = [h for _, h, _ in st.appended]
    assert source_ingest.SOURCE_SECTION in headings
    assert source_ingest.ANALYSIS_SECTION in headings
    # 자리표시 주제 → 분석의 suggested_topic으로 자동 발제
    assert card["topic"] == ANALYSIS["suggested_topic"]
    merged = {}
    for _pid, fields in st.updates:
        merged.update(fields)
    assert merged.get("topic") == ANALYSIS["suggested_topic"]


def test_ingest_pasted_text_keeps_real_topic(monkeypatch):
    """URL 없이 📎 소스 원문 붙여넣기 + 진짜 주제가 있으면 주제를 바꾸지 않는다."""
    st = IngestState(sections={("p1", source_ingest.SOURCE_SECTION): "붙여넣은 원문 " * 50})
    source_ingest.store = st
    monkeypatch.setattr(source_ingest.llm, "call_json", lambda *a, **k: dict(ANALYSIS))
    card = {"page_id": "p1", "topic": "받아쓰기 우는 아이", "source_url": "",
            "audience": ""}
    assert source_ingest.ingest(card) is True
    assert card["topic"] == "받아쓰기 우는 아이"           # 주제 유지
    assert not any("topic" in f for _, f in st.updates)
    assert any(h == source_ingest.ANALYSIS_SECTION for _, h, _ in st.appended)


def test_ingest_idempotent_skips_existing_analysis(monkeypatch):
    st = IngestState(sections={
        ("p1", source_ingest.SOURCE_SECTION): "원문",
        ("p1", source_ingest.ANALYSIS_SECTION): "기존 분석",
    })
    source_ingest.store = st
    called = []
    monkeypatch.setattr(source_ingest.llm, "call_json",
                        lambda *a, **k: called.append(1) or dict(ANALYSIS))
    card = {"page_id": "p1", "topic": "주제", "source_url": "https://x", "audience": ""}
    assert source_ingest.ingest(card) is True
    assert not called        # 분석 재실행 없음
    assert not st.appended   # 소스 재수집 없음


# ---------- run.handle_intake 연동 ----------

def _fake_manus(monkeypatch):
    import types
    fake = types.SimpleNamespace(
        available=lambda: False,
        claude_research_fallback=lambda topic, audience: [],
    )
    monkeypatch.setattr(run, "manus_research", fake)


def test_intake_ingest_failure_with_topic_continues(monkeypatch):
    st = IngestState()
    run.store = st
    source_ingest.store = st
    _fake_manus(monkeypatch)
    monkeypatch.setattr(run.source_ingest, "ingest",
                        lambda card: (_ for _ in ()).throw(RuntimeError("fetch 실패")))
    run.handle_intake({
        "page_id": "p1", "content_id": "DG-1", "idempotency_key": "",
        "topic": "진짜 주제", "audience": "학부모", "source_url": "https://x",
    })
    assert any("소스 수집에 실패" in m for _, m in st.notes)  # 경고 통지
    assert any("🆕" in m for _, m in st.notes)                # 그래도 접수 진행


def test_intake_ingest_failure_without_topic_raises(monkeypatch):
    st = IngestState()
    run.store = st
    source_ingest.store = st
    _fake_manus(monkeypatch)
    monkeypatch.setattr(run.source_ingest, "ingest",
                        lambda card: (_ for _ in ()).throw(RuntimeError("fetch 실패")))
    with pytest.raises(RuntimeError):
        run.handle_intake({
            "page_id": "p1", "content_id": "DG-1", "idempotency_key": "",
            "topic": "(소스) 벤치마킹 발제 대기", "audience": "",
            "source_url": "https://x",
        })
