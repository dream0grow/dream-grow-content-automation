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
    assert "16년차 초등교사" in html                        # 킥커(좌상단 문구)
    assert 'class="kicker"' in html
    assert f"font-size:{thumbnail.LINE_PX}px" in html       # 확정 폰트 크기 유지
    assert 'class="nophoto"' in html                        # bg 없으면 그라데이션 폴백


def test_thumb_html_fallback_and_escape():
    pick = {"line1": "", "copy": "<b>2가지만</b> 배우면", "label": ""}
    html = thumbnail.thumb_html(pick, bg="url('x')")
    assert "&lt;b&gt;" in html
    assert 'class="photo"' in html
    assert 'class="kicker"' not in html                     # label 없으면 킥커 생략


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


def test_develop_cell_variants_and_validation():
    cell = thumbnail.develop_cell(DEV, VALIDATION)
    assert cell.startswith("대입: (A) = 초등 고전 독서")
    assert "1. 고전을 만화책처럼 읽는 방법" in cell
    assert "(이 방법으로 하니 푹 빠집니다)" in cell
    assert "8/8/9/7/8 — 모델 추정" in cell
    assert "구조" not in cell.split("\n")[0]  # 구조분석은 J열 몫 — M에 반복하지 않음


def test_emotion_and_image_cells():
    assert thumbnail.emotion_cell("기대", 9, "문구 이유") == "(기대 9) 문구 이유"
    img = thumbnail.image_cell(DEV)
    assert "(기대) 데미안 들고 편안하게 읽는 아이 — 우리 아이도 기대" in img


# ---------- 열 해석 (헤더 이름 기반) ----------

HEADER = ["날짜 및 키워드", "영상 URL", "썸네일 이미지", "영상 제목", "상황", "고민", "욕구",
          "계획", "썸네일 문구  (기대, 증거, 의문, 공감)", "영상 문구 분석",
          "그림  (기대, 증거, 의문, 공감)", "내가 만들 영상 키워드", "키워드로 문구 디벨롭",
          "핫비디오 썸네일", "핫비디오 썸네일 분석", "핫비디오로 문구 디벨롭",
          "이미지 디벨롭", "만든 썸네일", "만든 제목", "", "영상요약", "핫비디오 영상 도입부"]


def test_resolve_columns_by_header_names():
    cols = thumbnail.resolve_columns(HEADER)
    assert cols["structure"] == 9          # J 영상 문구 분석
    assert cols["my_keyword"] == 11        # L
    assert cols["kw_develop"] == 12        # M 키워드로 문구 디벨롭
    assert cols["hot_thumb"] == 13 and cols["hot_analysis"] == 14
    assert cols["hot_develop"] == 15       # P
    assert cols["image_develop"] == 16 and cols["made_title"] == 18
    # 열이 한 칸 밀려도 이름으로 따라간다
    shifted = ["메모"] + HEADER
    assert thumbnail.resolve_columns(shifted)["structure"] == 10


def test_col_letter():
    assert thumbnail.col_letter(0) == "A"
    assert thumbnail.col_letter(12) == "M"
    assert thumbnail.col_letter(18) == "S"
    assert thumbnail.col_letter(26) == "AA"


# ---------- 시트 모드: 대기 행 탐지 + 빈 칸만 채우기 ----------

COLS = thumbnail.resolve_columns(HEADER)


def _row(k="", m="", url="", title="", situation="", j="", i_="", hot_a=""):
    row = [""] * 19
    row[COLS["my_keyword"]] = k
    row[COLS["kw_develop"]] = m
    row[COLS["url"]] = url
    row[COLS["title"]] = title
    row[COLS["situation"]] = situation
    row[COLS["structure"]] = j
    row[COLS["copy_emotion"]] = i_
    row[COLS["hot_analysis"]] = hot_a
    return row


def test_find_pending_rules():
    rows = [
        _row(k="초등 고전 독서", url="https://youtu.be/x"),   # 처리 대상
        _row(k="키워드만 있고 단서 없음"),                     # URL·제목 없음 → 제외
        _row(k="이미 처리", m="1. ...", url="u"),              # M 채워짐 → 제외
        _row(url="https://youtu.be/y"),                        # 키워드 없음 → 제외
        _row(k="제목만 있는 행", title="벤치 제목"),           # 처리 대상
    ]
    assert thumbnail.find_pending(rows, COLS) == [0, 4]


def test_find_structure_backfill_skips_duplicates_and_filled():
    rows = [
        _row(url="u1", title="t1", i_="(기대 9) ..."),         # 대상
        _row(url="u1", title="t1", i_="(기대 9) ..."),         # 위와 같은 영상(묶임) → 패스
        _row(url="u2", title="t2", j="구조 : ...", i_="x"),    # J 이미 있음 → 패스
        _row(title="t3", i_="(기대 10) ..."),                  # 대상 (제목만)
        _row(),                                                # 단서 없음 → 패스
    ]
    assert thumbnail.find_structure_backfill(rows, COLS, skip=set()) == [0, 3]
    # 전체 처리 예정(skip) 행은 백필에서 제외
    assert thumbnail.find_structure_backfill(rows, COLS, skip={0}) == [3]


def test_row_updates_fills_only_empty_cells():
    row = _row(k="초등 고전 독서", url="u", situation="사람이 이미 쓴 상황")
    result = {"analysis": ANALYSIS, "develop": DEV, "expand": {"validation": VALIDATION}}
    hot = {"hot_structure": "(A) 구조", "develops": [{"copy": "핫문구", "title": "핫제목", "note": "욕구 연결"}]}
    upd = thumbnail._row_updates(row, COLS, result, {"copy": "벤치 문구", "image": "벤치 그림"}, hot)
    assert "E" not in upd                        # 이미 채워진 상황 칸은 건드리지 않음
    assert upd["F"] == "고민B" and upd["G"] == "욕구C" and upd["H"] == "계획D"
    assert upd["I"].startswith("(기대 9) 벤치 문구")
    assert upd["J"].startswith("구조 : (원하는 A)을 (쉬운 B)처럼 하는 방법")
    assert upd["K"].startswith("(기대 1)")
    assert upd["M"].startswith("대입:") and "검증" in upd["M"]  # M: 키워드로 문구 디벨롭
    assert "핫문구" in upd["P"] and "핫비디오 구조" in upd["P"]  # P: 핫비디오로 문구 디벨롭
    assert "(기대) 데미안" in upd["Q"]
    assert upd["S"] == "최종 제목1"


def test_expansion_values_inherit_parent_and_set_keyword():
    parent = _row(k="초등 고전 독서", url="https://youtu.be/x", title="벤치 제목",
                  situation="부모 상황", j="구조 : ...", i_="(기대 9) ...")
    expand = {
        "expansions": [{"keyword": "초등 영어 원서", "why": "학부모가 방법을 원함",
                        "viewer": {"situation": "원서 상황", "worry": "w", "desire": "d", "plan": "p"},
                        "develops": [{"copy": "원서를 동화책처럼 읽는 법", "title": "제목"}]}],
        "validation": [{"keyword": "초등 영어 원서", "copy": "원서를 동화책처럼 읽는 법",
                        "situation": 7, "worry": 7, "desire": 8, "plan": 6,
                        "desire_intensity": 7, "evidence": "모델 추정"}],
    }
    rows = thumbnail.expansion_values(expand, parent, COLS)
    assert len(rows) == 1
    r = rows[0]
    assert r[COLS["url"]] == "https://youtu.be/x"        # 벤치마크 상속
    assert r[COLS["title"]] == "벤치 제목"
    assert r[COLS["structure"]] == "구조 : ..."
    assert r[COLS["situation"]] == "원서 상황"           # 확장 키워드 시청자 분석이 우선
    assert r[COLS["my_keyword"]] == "초등 영어 원서"      # 3) L열 키워드가 핵심
    m = r[COLS["kw_develop"]]                            # 4) M열 디벨롭
    assert m.startswith("(자동 확장") and "원서를 동화책처럼 읽는 법" in m and "검증" in m


def test_hot_develop_cell_and_structure_cell():
    hot = {"hot_structure": "(A)의 폭로 구조 *주의: ...",
           "develops": [{"copy": "문구1", "title": "제목1", "note": "고민 연결"}]}
    cell = thumbnail.hot_develop_cell(hot)
    assert cell.startswith("핫비디오 구조 :") and "1. 문구1" in cell and "→ 고민 연결" in cell
    s = thumbnail.structure_cell(ANALYSIS)
    assert s.startswith("구조 : (원하는 A)") and "(제목:" in s and "*주의:" in s


def test_hot_video_develop_returns_none_without_material(monkeypatch):
    called = []
    monkeypatch.setattr(thumbnail.llm, "call_json", lambda *a, **k: called.append(1) or {})
    assert thumbnail.hot_video_develop("주제", _row(), COLS) is None
    assert not called                                     # 재료 없으면 LLM 호출도 없음


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


# ---------- 렌더 확정 (색칠 = 수정·확인 완료) ----------

def test_parse_made_title():
    copy, title = thumbnail.parse_made_title(
        "고전을 만화책처럼\n읽는 법\n(이 방법으로 읽으니 아이가 고전을 다 읽었습니다)")
    assert copy == "고전을 만화책처럼 읽는 법"
    assert title == "이 방법으로 읽으니 아이가 고전을 다 읽었습니다"
    # 괄호 없으면 전체가 문구
    assert thumbnail.parse_made_title("문구만 있음") == ("문구만 있음", "")
    assert thumbnail.parse_made_title("") == ("", "")


def test_is_colored():
    from orchestrator import gsheet
    assert not gsheet.is_colored(None)              # 기본(무색)
    assert not gsheet.is_colored((1.0, 1.0, 1.0))   # 흰색
    assert gsheet.is_colored((1.0, 0.95, 0.8))      # 연노랑 (스크린샷 색)
    assert gsheet.is_colored((0.85, 0.92, 0.83))    # 연녹색


def test_find_render_ready_requires_both_colors_and_empty_r():
    yellow, none = (1.0, 0.95, 0.8), None
    r0 = _row(k="초등 고전 독서")
    r0[COLS["made_title"]] = "고전을 만화책처럼 읽는 법\n(제목)"
    r1 = [c for c in r0]                       # 한쪽만 색칠 → 제외
    r2 = [c for c in r0]                       # 둘 다 색칠 + R 채워짐 → 제외
    r2 = list(r2); r2[COLS["made_thumb"]] = "https://..."
    r3 = _row()                                # S 비어 있음 → 제외
    rows = [list(r0), r1, r2, r3]
    bgs = [[yellow, yellow], [yellow, none], [yellow, yellow], [yellow, yellow]]
    assert thumbnail.find_render_ready(rows, COLS, bgs) == [0]


def test_save_render_to_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path / "vault"))
    png = tmp_path / "a.png"; png.write_bytes(b"png")
    jpg = tmp_path / "a.jpg"; jpg.write_bytes(b"jpg")
    rel = thumbnail.save_render_to_vault("초등 고전 독서", png, jpg)
    assert rel.startswith("파이프라인/썸네일/") and rel.endswith(".png")
    assert (tmp_path / "vault" / rel).read_bytes() == b"png"
    assert (tmp_path / "vault" / rel.replace(".png", ".jpg")).read_bytes() == b"jpg"
    # 같은 날 같은 주제 재렌더 → -1 파일로 보존
    rel2 = thumbnail.save_render_to_vault("초등 고전 독서", png, jpg)
    assert rel2 != rel and rel2.endswith("-1.png")


def test_color_cells_builds_repeat_cell_requests(monkeypatch):
    from orchestrator import gsheet
    captured = {}
    monkeypatch.setattr(gsheet, "batch_update", lambda reqs: captured.setdefault("reqs", reqs))
    monkeypatch.setenv("DG_THUMB_SHEET_GID", "787785781")
    gsheet.color_cells(13, [16, 18], thumbnail.DONE_BLUE)
    reqs = captured["reqs"]
    assert len(reqs) == 2
    rng = reqs[0]["repeatCell"]["range"]
    assert rng["startRowIndex"] == 12 and rng["endRowIndex"] == 13   # 13행
    assert rng["startColumnIndex"] == 16 and rng["endColumnIndex"] == 17  # Q열
    bg = reqs[1]["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"]
    assert abs(bg["blue"] - 0.973) < 1e-6                            # 파랑(작업 완료)
    assert reqs[0]["repeatCell"]["fields"] == "userEnteredFormat.backgroundColor"


def test_find_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail, "ASSETS_DIR", tmp_path)
    d = tmp_path / "초등고전독서"; d.mkdir()
    (d / "demian.jpg").write_bytes(b"x")
    (d / "note.txt").write_bytes(b"x")           # 이미지 아닌 파일은 제외
    assert thumbnail.find_assets("초등 고전 독서") == [str(d / "demian.jpg")]
    assert thumbnail.find_assets("없는 키워드") == []
