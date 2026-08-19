"""유튜브 썸네일 자동화(thumbnail) 단위테스트.

실행: python3 -m pytest orchestrator/test_thumbnail.py -q
"""
import pytest

from orchestrator import thumbnail


# ---------- 패턴 라이브러리 (사전 작업 자산) ----------

def test_patterns_file_has_core_sections():
    text = thumbnail.load_patterns()
    for must in ("상황", "고민", "욕구", "계획", "기대", "증거", "의문", "공감", "구조 공식"):
        assert must in text, f"패턴 라이브러리에 '{must}' 섹션/키워드가 없음"


# ---------- 렌더 HTML ----------

PICK = {
    "category": "의문",
    "line1": "딱 ==이것==만 보면",
    "line2": "책 좋아할 아이인지 알아요",
    "label": "16년차 초등교사",
    "copy": "딱 '이것'만 보면 책 좋아할 아이인지 알아요",
    "photo_query": "korean teacher classroom",
    "photo_prompt": "",
}


def test_thumb_html_layout_and_highlight():
    html = thumbnail.thumb_html(PICK, bg="")
    assert "1280px" in html and "720px" in html
    assert '<span class="hl">이것</span>' in html          # ==강조== 변환
    assert "16년차 초등교사" in html                        # 신뢰 칩
    assert 'class="nophoto"' in html                        # bg 없으면 그라데이션 폴백
    assert "책 좋아할 아이인지 알아요" in html


def test_thumb_html_fallback_to_copy_and_escape():
    pick = {"category": "기대", "line1": "", "copy": "<b>2가지만</b> 배우면", "label": ""}
    html = thumbnail.thumb_html(pick, bg="url('x')")
    assert "&lt;b&gt;" in html                              # HTML 이스케이프
    assert 'class="photo"' in html                          # bg 있으면 사진 레이어
    assert 'class="chip"' not in html                       # label 없으면 칩 생략


# ---------- 산출물 md (시트 구조 미러) ----------

DATA = {
    "analysis": {"situation": "상황A", "worry": "고민B", "desire": "욕구C", "plan": "계획D"},
    "candidates": [
        {"category": "기대", "copy": "문구1", "structure": "구조1",
         "psychology": "심리1", "image_desc": "그림1"},
    ],
}
PICKS = [
    {"category": "의문", "copy": "픽문구", "structure": "픽구조", "title": "픽제목",
     "image_desc": "픽그림", "develop_note": "메모"},
]


def test_build_md_mirrors_sheet_columns():
    md = thumbnail.build_md("초등 고전 독서", "초등 학부모", DATA, PICKS,
                            benchmark_copy="벤치문구", benchmark_url="https://yt")
    assert "| 상황A | 고민B | 욕구C | 계획D |" in md
    assert "| 의문 | 픽문구 | 픽구조 | 픽제목 | 픽그림 | 메모 |" in md
    assert "| 기대 | 문구1 | 구조1 | 심리1 | 그림1 |" in md
    assert "벤치문구" in md and "https://yt" in md


def test_build_md_sanitizes_pipes_and_newlines():
    data = {"analysis": {"situation": "a|b\nc", "worry": "", "desire": "", "plan": ""},
            "candidates": []}
    md = thumbnail.build_md("주제", "타겟", data, [])
    assert "a／b c" in md   # 표 깨짐 방지


# ---------- 볼트 저장 (script_feedback 핑퐁 계약) ----------

def test_save_to_review_frontmatter_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    name = thumbnail.save_to_review("초등 고전 독서", "# 본문\n")
    p = tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기" / name
    assert p.exists() and name == "썸네일_초등고전독서.md"

    from vault_pipeline.vault_io import parse_frontmatter
    meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
    # script_feedback 알림 조건: 검수상태=대기 + 최근 생성일 (+ 상태가 완료류 아님)
    assert str(meta.get("검수상태")) == "대기"
    assert meta.get("생성일")
    assert meta.get("type") == "thumbnail"
    assert "# 본문" in body

    # 같은 주제 재실행 시 덮어쓰지 않고 -2 파일
    name2 = thumbnail.save_to_review("초등 고전 독서", "# 본문2\n")
    assert name2 == "썸네일_초등고전독서-2.md"


def test_develop_raises_on_empty_picks(monkeypatch):
    monkeypatch.setattr(thumbnail.llm, "call_json", lambda *a, **k: {"picks": []})
    with pytest.raises(RuntimeError):
        thumbnail.develop("주제", "타겟", DATA)


def test_generate_raises_on_empty_candidates(monkeypatch):
    monkeypatch.setattr(thumbnail.llm, "call_json", lambda *a, **k: {"candidates": []})
    with pytest.raises(RuntimeError):
        thumbnail.generate_candidates("주제", "타겟")
