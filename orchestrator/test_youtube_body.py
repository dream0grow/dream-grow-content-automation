"""유튜브 도입부→본문 자동 완성(youtube_body) 단위테스트.

실행: python3 -m pytest orchestrator/test_youtube_body.py -q
"""
import pytest

from orchestrator import youtube_body


INTRO = ("여러분, 고전 책 읽으려고 해보세요. 혹시 고전 읽기를 하려고 20만원 되는 "
         "클래스 등록하고 있습니까? 클래스 다니는 게 잘못되었다는 건 아니에요. "
         "결국 책이 재미있어져야 합니다.")

HEADER = ([""] * 4 + ["상황", "고민", "욕구", "계획"] + [""] * 3
          + ["내가 만들 영상 키워드", "키워드로 문구 디벨롭"] + [""] * 5
          + ["만든 제목"] + [""] * 4 + ["만든 도입부", "완성 원고"])


def _row(intro=INTRO, title="초등 고전 독서를 만화책처럼 읽는 방법\n(2안) 다른 제목",
         keyword="초등 고전 독서"):
    row = [""] * 26
    row[0] = "2026.8.19. 영어공부"
    row[4], row[5], row[6], row[7] = "상황A", "고민B", "욕구C", "계획D"
    row[11], row[12] = keyword, "대입: A=고전, B=만화책"
    row[18], row[23] = title, intro
    return row


# ---------- 열/헤더 해석 ----------

def test_resolve_columns_by_header_names():
    # 열이 옮겨져도 헤더 이름으로 따라간다
    header = ["날짜", "", "만든 제목", "만든 도입부", "완성 원고", "내가 만들 키워드"]
    cols = youtube_body.resolve_columns(header)
    assert cols["made_title"] == 2
    assert cols["intro"] == 3
    assert cols["result"] == 4
    assert cols["my_keyword"] == 5


def test_resolve_columns_result_falls_back_next_to_intro():
    header = ["날짜"] + [""] * 22 + ["만든 도입부"]
    cols = youtube_body.resolve_columns(header)
    assert cols["intro"] == 23
    assert cols["result"] == 24  # 「완성 원고」열이 없으면 도입부 오른쪽


def test_find_header_row_skips_leading_blank_rows():
    rows = [[""] * 5, HEADER, _row()]
    assert youtube_body.find_header_row(rows) == 1


# ---------- 대기 행 탐지 + 장부 ----------

def test_find_pending_requires_intro_and_skips_ledger():
    rows = [HEADER, _row(), _row(intro="짧은 메모"), _row()]
    cols = youtube_body.resolve_columns(HEADER)
    # 장부 없음 → 도입부가 실제로 긴 행(1, 3)만
    assert youtube_body.find_pending(rows, cols, 0, {}) == [1, 3]
    # 행2(rownum=2)가 장부에 같은 해시로 기록되면 제외 (구형 문자열·신형 dict 모두)
    ledger = {"2": youtube_body.intro_hash(INTRO)}
    assert youtube_body.find_pending(rows, cols, 0, ledger) == [3]
    ledger = {"2": {"hash": youtube_body.intro_hash(INTRO), "card": "DG-x.md"}}
    assert youtube_body.find_pending(rows, cols, 0, ledger) == [3]
    # 도입부를 고치면 해시가 달라져 다시 잡힌다
    rows[1] = _row(intro=INTRO + " 수정했습니다. 완전히 새로운 접근이 필요해요.")
    assert youtube_body.find_pending(rows, cols, 0, ledger) == [1, 3]


def test_intro_hash_ignores_whitespace_only_changes():
    assert youtube_body.intro_hash("가나 다\n라") == youtube_body.intro_hash("가나다라")
    assert youtube_body.intro_hash("가나다라") != youtube_body.intro_hash("가나다라마")


# ---------- 맥락 추출 + 원고 조립 ----------

def test_row_context_uses_first_title_line():
    cols = youtube_body.resolve_columns(HEADER)
    ctx = youtube_body.row_context(_row(), cols)
    assert ctx["title"] == "초등 고전 독서를 만화책처럼 읽는 방법"
    assert ctx["keyword"] == "초등 고전 독서"
    assert "상황A" in ctx["viewer"] and "고민B" in ctx["viewer"]
    assert ctx["intro"] == INTRO


def test_assemble_script_keeps_intro_verbatim():
    ctx = {"title": "제목", "intro": INTRO}
    script = youtube_body.assemble_script(ctx, "## 📄 본문\n본문 내용")
    assert INTRO in script  # 사용자 도입부는 한 글자도 안 바뀐다
    assert script.index(INTRO) < script.index("## 📄 본문")


def test_extract_body_returns_body_and_closing_without_memo():
    script = ("# 영상 원고 -- t\n\n## 🎬 도입부 (0:00~0:30) — 사용자 원문\n\n도입\n\n"
              "## 📄 본문\n\n[00:30] 섹션 내용\n\n## 🏁 마무리\n\n요약 문장\n\n"
              "## 📋 제작 메모\n\n- B롤 아이디어\n")
    body = youtube_body.extract_body(script)
    assert body.startswith("## 📄 본문")
    assert "요약 문장" in body       # 마무리 포함
    assert "도입" not in body        # 도입부 제외 (X열에 이미 있음)
    assert "제작 메모" not in body   # 내부 메모 제외
    assert youtube_body.extract_body("본문 헤딩 없는 텍스트") == ""




# ---------- 생성 가드 ----------

def test_generate_rejects_too_short(monkeypatch):
    monkeypatch.setattr(youtube_body.llm, "call_writing", lambda *a, **k: "짧음")
    monkeypatch.setattr(youtube_body.prompts, "get_system", lambda *a, **k: "")
    ctx = {"title": "t", "keyword": "k", "intro": INTRO,
           "viewer": "", "develop": ""}
    with pytest.raises(RuntimeError):
        youtube_body.generate_messages(ctx, "학부모")
    with pytest.raises(RuntimeError):
        youtube_body.generate_body(ctx, "메시지", "학부모")


# ---------- 행 처리 끝까지 (실제 볼트 저장) ----------

def test_process_row_creates_card_and_review_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.setattr(youtube_body.prompts, "get_system", lambda *a, **k: "")
    long_body = "## 📄 본문\n[00:30] 섹션\n" + "본문 문장입니다. " * 60 + "\n## 🏁 마무리\n요약"
    calls = []

    def fake_writing(prompt, **kw):
        calls.append(prompt)
        return ("# 필수 메시지 정리\n## 한 줄 주장\n- 주장" + " 내용" * 60
                if len(calls) == 1 else long_body)

    monkeypatch.setattr(youtube_body.llm, "call_writing", fake_writing)

    cols = youtube_body.resolve_columns(HEADER)
    result = youtube_body.process_row(_row(), cols, rownum=13, audience="초등 학부모")

    # ① 활성 카드 생성 — 파일명은 main 통일 규칙(card_filename), 재처리되지 않는 상태
    cards = list((tmp_path / "파이프라인" / "활성").glob("*.md"))
    assert len(cards) == 1
    assert cards[0].name.startswith("원고_YT롱폼_독서_")
    assert cards[0].name.endswith("_DG-2026-0001.md")
    assert result["body_text"].startswith("## 📄 본문")
    text = cards[0].read_text(encoding="utf-8")
    assert "stage: draft" in text
    assert "status: needs_human" in text
    assert "format: youtube" in text
    assert INTRO in text                      # 도입부 원문 보존
    assert "필수 메시지 정리" in text
    # ② 본문 생성 프롬프트에 1차 산출물(메시지 설계)이 주입됐다
    assert "한 줄 주장" in calls[1]
    # ③ 05 리뷰/대기 사본 → script_feedback 텔레그램 핑퐁 시작점
    review = list((tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기").glob("원고_YT롱폼_*.md"))
    assert len(review) == 1
    assert result["review"] == review[0].name


def test_sync_ledger_rows_backfills_empty_link_and_body(tmp_path, monkeypatch):
    """Z열(본문)을 나중에 만든 경우 — 처리 완료 행의 빈 칸을 카드에서 백필한다."""
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    card_name = "DG-2026-0049 원고_YT롱폼_독서_초등+고전+독서.md"
    card_dir = tmp_path / "파이프라인" / "활성"
    card_dir.mkdir(parents=True)
    (card_dir / card_name).write_text(
        "---\ntopic: t\n---\n\n## ✍️ 영상 원고\n\n# 영상 원고 -- t\n\n"
        "## 🎬 도입부\n\n도입\n\n## 📄 본문\n\n[00:30] 백필될 본문\n\n"
        "## 🏁 마무리\n\n요약\n\n## 📋 제작 메모\n\n- 메모\n", encoding="utf-8")

    cols = youtube_body.resolve_columns(HEADER)
    rows = [HEADER, _row()]  # 행2: Y·Z 비어 있음
    ledger = {"2": {"hash": youtube_body.intro_hash(INTRO), "card": card_name}}
    written = {}
    monkeypatch.setattr(youtube_body.gsheet, "update",
                        lambda a1, values, title=None: written.update({a1: values[0][0]}))

    youtube_body.sync_ledger_rows(rows, cols, ledger, "분석")
    y = youtube_body.col_letter(cols["result"])
    z = youtube_body.col_letter(cols["body"])
    assert card_name.split(" ")[0] in written[f"{y}2"]  # 카드 링크
    assert written[f"{z}2"].startswith("## 📄 본문")
    assert "제작 메모" not in written[f"{z}2"]

    # 도입부가 바뀐 행은 백필하지 않는다 (재생성 대상)
    written.clear()
    rows[1] = _row(intro=INTRO + " 완전히 새로 고친 도입부입니다. 다시 생성돼야 해요.")
    youtube_body.sync_ledger_rows(rows, cols, ledger, "분석")
    assert not written


def test_run_sheet_skips_without_service_account(monkeypatch, capsys):
    monkeypatch.delenv("GSHEET_SA_JSON", raising=False)
    youtube_body.run_sheet("학부모")
    assert "GSHEET_SA_JSON 미설정" in capsys.readouterr().out
