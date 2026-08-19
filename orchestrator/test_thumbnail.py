"""유튜브 썸네일 자동화(thumbnail) 단위테스트.

실행: python3 -m pytest orchestrator/test_thumbnail.py -q
"""
import pytest

from orchestrator import thumbnail


# ---------- 패턴 라이브러리 (6단계 방법론 자산) ----------

def test_patterns_file_has_methodology():
    text = thumbnail.load_patterns()
    for must in ("1단계", "2단계", "3단계", "4단계", "5단계", "6단계",
                 "기대", "의문", "증거", "공감", "10", "구조 공식", "주의할 점"):
        assert must in text, f"패턴 라이브러리에 '{must}'가 없음"
    # 감정을 그대로 가져간다는 대원칙
    assert "감정을 그대로 가져간다" in text


# ---------- 벤치마크 URL 파싱 ----------

def test_video_id_variants():
    assert thumbnail.video_id("https://www.youtube.com/watch?v=812bblPpXFQ") == "812bblPpXFQ"
    assert thumbnail.video_id("https://youtu.be/abc123xyz") == "abc123xyz"
    assert thumbnail.video_id("https://www.youtube.com/watch?v=8nHxEdnbIm0&t=4s") == "8nHxEdnbIm0"
    assert thumbnail.video_id("") == ""
    assert thumbnail.video_id("not a url") == ""


# ---------- 렌더 HTML ----------

PICK = {
    "copy": "초등 고전 독서를 만화책처럼 읽는 방법",
    "line1": "==고전==을 만화책처럼", "line2": "읽는 방법",
    "label": "16년차 초등교사",
    "photo_query": "korean child reading", "photo_prompt": "",
}


def test_thumb_html_layout_and_highlight():
    html = thumbnail.thumb_html(PICK, bg="")
    assert "1280px" in html and "720px" in html
    assert '<span class="hl">고전</span>' in html          # ==강조== 변환
    assert "16년차 초등교사" in html                        # 신뢰 칩
    assert 'class="nophoto"' in html                        # bg 없으면 그라데이션 폴백


def test_thumb_html_fallback_and_escape():
    pick = {"line1": "", "copy": "<b>2가지만</b> 배우면", "label": ""}
    html = thumbnail.thumb_html(pick, bg="url('x')")
    assert "&lt;b&gt;" in html
    assert 'class="photo"' in html
    assert 'class="chip"' not in html                       # label 없으면 칩 생략


# ---------- 시트 셀 생성 ----------

ANALYSIS = {
    "viewer": {"situation": "상황A", "worry": "고민B", "desire": "욕구C", "plan": "계획D"},
    "emotion": {"copy_category": "기대", "copy_score": 9,
                "image_category": "기대", "image_score": 1, "reason": "이유"},
    "structure": {"copy_structure": "(원하는 A)을 (쉬운 B)처럼 하는 방법",
                  "title_structure": "이 방법으로 하니 (A)를 다 해결했습니다",
                  "caution": "A는 어렵다고 느끼는 것", "library_no": "1"},
    "desire_mapping": "영어 실력 → 고전 독서",
}
DEV = {
    "variable_mapping": "(A) = 초등 고전 독서",
    "my_viewer": {"situation": "s", "worry": "w", "desire": "d", "plan": "p"},
    "develops": [
        {"copy": "고전을 만화책처럼 읽는 방법", "title": "이 방법으로 하니 푹 빠집니다", "note": "기대 증폭"},
        {"copy": "고전을 그림책처럼 읽는 방법", "title": "제목2", "note": ""},
    ],
    "image_ideas": [
        {"category": "기대", "idea": "데미안 들고 편안하게 읽는 아이", "reason": "우리 아이도 기대"},
        {"category": "의문", "idea": "", "reason": "효과적이지 않음 — 제외"},
    ],
    "picks": [dict(PICK, title="최종 제목1")],
}
VALIDATION = [{"keyword": "초등 고전 독서", "copy": "고전을 만화책처럼 읽는 방법",
               "situation": 8, "worry": 8, "desire": 9, "plan": 7,
               "desire_intensity": 8, "evidence": "모델 추정"}]


def test_develop_cell_contains_structure_variants_validation():
    cell = thumbnail.develop_cell(ANALYSIS, DEV, VALIDATION)
    assert "구조: (원하는 A)을 (쉬운 B)처럼 하는 방법" in cell
    assert "*주의: A는 어렵다고 느끼는 것" in cell
    assert "1. 고전을 만화책처럼 읽는 방법" in cell
    assert "(이 방법으로 하니 푹 빠집니다)" in cell
    assert "8/8/9/7/8 — 모델 추정" in cell


def test_emotion_and_image_cells():
    assert thumbnail.emotion_cell("기대", 9, "문구 이유") == "(기대 9) 문구 이유"
    img = thumbnail.image_cell(DEV)
    assert "(기대) 데미안 들고 편안하게 읽는 아이 — 우리 아이도 기대" in img


# ---------- 시트 모드: 대기 행 탐지 + 빈 칸만 채우기 ----------

def _row(k="", n="", url="", title="", situation=""):
    row = [""] * 17
    row[thumbnail.COL["my_keyword"]] = k
    row[thumbnail.COL["copy_develop"]] = n
    row[thumbnail.COL["url"]] = url
    row[thumbnail.COL["title"]] = title
    row[thumbnail.COL["situation"]] = situation
    return row


def test_find_pending_rules():
    rows = [
        _row(k="초등 고전 독서", url="https://youtu.be/x"),   # 처리 대상
        _row(k="키워드만 있고 단서 없음"),                     # URL·제목 없음 → 제외
        _row(k="이미 처리", n="구조: ...", url="u"),           # N 채워짐 → 제외
        _row(url="https://youtu.be/y"),                        # 키워드 없음 → 제외
        _row(k="제목만 있는 행", title="벤치 제목"),           # 처리 대상
    ]
    assert thumbnail.find_pending(rows) == [0, 4]


def test_row_updates_fills_only_empty_cells():
    row = _row(k="초등 고전 독서", url="u", situation="사람이 이미 쓴 상황")
    result = {"analysis": ANALYSIS, "develop": DEV, "expand": {"validation": VALIDATION}}
    upd = thumbnail._row_updates(row, result, {"copy": "벤치 문구", "image": "벤치 그림"})
    assert "E" not in upd                      # 이미 채워진 상황 칸은 건드리지 않음
    assert upd["F"] == "고민B" and upd["G"] == "욕구C" and upd["H"] == "계획D"
    assert upd["I"].startswith("(기대 9) 벤치 문구")
    assert upd["J"].startswith("(기대 1)")
    assert "구조:" in upd["N"] and "검증" in upd["N"]
    assert "(기대) 데미안" in upd["O"]
    assert upd["Q"] == "최종 제목1"


def test_expansion_rows_layout():
    expand = {
        "expansions": [{"keyword": "초등 영어 원서", "why": "학부모가 방법을 원함",
                        "viewer": {"situation": "s", "worry": "w", "desire": "d", "plan": "p"},
                        "develops": [{"copy": "원서를 동화책처럼 읽는 법", "title": "제목"}]}],
        "validation": [{"keyword": "초등 영어 원서", "copy": "원서를 동화책처럼 읽는 법",
                        "situation": 7, "worry": 7, "desire": 8, "plan": 6,
                        "desire_intensity": 7, "evidence": "모델 추정"}],
    }
    rows = thumbnail.expansion_rows(expand, "2026-08-19")
    assert len(rows) == 1
    r = rows[0]
    assert r[thumbnail.COL["date_kw"]] == "2026-08-19 초등 영어 원서 (자동 확장)"
    assert r[thumbnail.COL["my_keyword"]] == "초등 영어 원서"
    assert "원서를 동화책처럼 읽는 법" in r[thumbnail.COL["copy_develop"]]
    assert "검증" in r[thumbnail.COL["copy_develop"]]
    assert r[thumbnail.COL["situation"]] == "s"


# ---------- md 산출물 ----------

def test_build_md_covers_all_stages():
    md = thumbnail.build_md("초등 고전 독서", "초등 학부모",
                            {"copy": "영어 문장 한글처럼 읽는 법", "title": "벤치 제목", "url": "u"},
                            ANALYSIS, DEV,
                            {"expansions": [{"keyword": "kw", "why": "이유",
                                             "develops": [{"copy": "c", "title": "t"}]}],
                             "validation": VALIDATION})
    for must in ("1단계", "2단계", "3단계", "4단계", "5단계", "6단계",
                 "기대 9", "| 상황A | 고민B | 욕구C | 계획D |",
                 "고전을 만화책처럼 읽는 방법", "모델 추정"):
        assert must in md, f"md에 '{must}' 없음"


# ---------- 볼트 저장 (script_feedback 핑퐁 계약) ----------

def test_save_to_review_frontmatter_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    name = thumbnail.save_to_review("초등 고전 독서", "# 본문\n")
    p = tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기" / name
    assert p.exists() and name == "썸네일_초등고전독서.md"
    from vault_pipeline.vault_io import parse_frontmatter
    meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
    assert str(meta.get("검수상태")) == "대기"
    assert meta.get("생성일")
    assert meta.get("type") == "thumbnail"
    # 같은 주제 재실행 시 덮어쓰지 않고 -2 파일
    assert thumbnail.save_to_review("초등 고전 독서", "x") == "썸네일_초등고전독서-2.md"


# ---------- 실패 가드 ----------

def test_analyze_raises_on_empty_structure(monkeypatch):
    monkeypatch.setattr(thumbnail.llm, "call_json", lambda *a, **k: {})
    with pytest.raises(RuntimeError):
        thumbnail.analyze("주제", "타겟", {})


def test_develop_raises_on_empty(monkeypatch):
    monkeypatch.setattr(thumbnail.llm, "call_json", lambda *a, **k: {"develops": []})
    with pytest.raises(RuntimeError):
        thumbnail.develop("주제", "타겟", ANALYSIS)


def test_run_sheet_skips_without_credentials(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("GSHEET_SA_JSON", raising=False)
    thumbnail.run_sheet("타겟", 0, tmp_path, [])
    assert "GSHEET_SA_JSON 미설정" in capsys.readouterr().out
