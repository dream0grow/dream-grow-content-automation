"""유튜브 썸네일 자동화 — 벤치마킹 6단계 방법론 + 구글 시트 직접 읽기/쓰기.

사용자의 벤치마킹 시트 워크플로우를 그대로 코드로 옮겼다:
  1단계 썸네일을 보는 사람 분석 (상황/고민/욕구/계획)
  2단계 썸네일이 불러일으키는 감정 분석 (기대/의문/증거/공감 — 문구+그림 합쳐 10점 배분)
  3단계 썸네일 문구 + 제목 세트 구조분석 ((변수) 분해 + 주의할 점)
  4단계 구조에 내 키워드 대입 — 같은 감정을 증폭하는 방향으로 변주 6~10개 + 이미지 디벨롭
  5단계 타겟이 '방법'을 원하는 다른 키워드 확장 (같은 구조·같은 감정)
  6단계 검증 — 만든 문구가 상황/고민/욕구/계획에 연결되는지 점수화 (근거 없으면 '모델 추정' 표기)
  + 최종 픽을 1280×720 PNG/JPG로 렌더 (cardnews 사진 소스 재사용)

실행 모드:
  ① 시트 모드 (기본 자동화): `--sheet`
     구글 시트(분석 탭)에서 "내가 만들 영상 키워드(K)"가 있고 "문구 디벨롭(N)"이 빈 행을 찾아
     벤치마킹 썸네일을 비전 OCR로 읽고 1~6단계 실행 → 그 행의 상황/고민/욕구/계획·문구/그림
     감정 분석·문구 디벨롭·이미지 디벨롭·만든 제목 칸에 결과를 써넣는다 (빈 칸만 채움).
     5단계 확장 키워드는 아래에 새 행으로 추가. 인증: GSHEET_SA_JSON (orchestrator/gsheet.py).
  ② 수동 모드: `--topic "초등 고전 독서" --benchmark-copy "..." --benchmark-title "..."`

산출물: out/thumb_XX.png(+jpg), thumbnail_plan.json, 썸네일_{주제}.md
+ 볼트 `05 리뷰/대기/썸네일_{주제}.md` (텔레그램 알림·답장 핑퐁, --no-vault로 끔)
"""
import argparse
import html as _html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import gsheet, llm, prompts
from orchestrator.cardnews import chrome_path, ensure_fonts, resolve_photo

W, H = 1280, 720
PATTERNS_FILE = Path(__file__).resolve().parent.parent / "data" / "thumbnail_patterns.md"
# 원고 핑퐁과 같은 폴더 — script_feedback이 `검수상태: 대기` + 최근 생성일이면 알림을 보낸다
REVIEW_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"

# 분석 탭 열 배치 (A1 표기). 시트 구조가 바뀌면 여기만 고친다.
COL = {"date_kw": 0, "url": 1, "thumb_img": 2, "title": 3,
       "situation": 4, "worry": 5, "desire": 6, "plan": 7,          # E~H
       "copy_emotion": 8, "image_emotion": 9, "my_keyword": 10,     # I,J,K
       "copy_develop": 13, "image_develop": 14, "made_title": 16}   # N,O,Q
LAST_COL = "Q"


def log(msg: str):
    print(f"[thumbnail] {msg}", flush=True)


def load_patterns() -> str:
    return PATTERNS_FILE.read_text(encoding="utf-8")


def _file_token(s: str) -> str:
    return re.sub(r"\s+", "", re.sub(r'[\\/:*?"<>|#^\[\]]', "", s or "")).strip()


# ---------- 벤치마킹 썸네일 읽기 (비전 OCR) ----------

def video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{6,})", url or "")
    return m.group(1) if m else ""


def ocr_benchmark(url: str) -> dict:
    """유튜브 썸네일 이미지에서 문구·그림 묘사를 비전으로 읽는다. 실패 시 {}."""
    import urllib.request
    vid = video_id(url)
    if not vid:
        return {}
    img = b""
    for name in ("maxresdefault", "hqdefault"):
        try:
            req = urllib.request.Request(
                f"https://i.ytimg.com/vi/{vid}/{name}.jpg",
                headers={"User-Agent": "dreamgrow-thumbnail"})
            with urllib.request.urlopen(req, timeout=30) as r:
                img = r.read()
            if len(img) > 2000:  # hqdefault 404는 회색 placeholder(1~2KB)로 온다
                break
        except Exception:
            continue
    if len(img) <= 2000:
        return {}
    text = llm.call_vision(
        "이 유튜브 썸네일을 분석하세요. JSON만 출력: "
        '{"copy": "화면에 적힌 문구를 줄바꿈 포함 그대로", '
        '"image": "그림 묘사 — 인물(누가, 표정, 동작)·소품·구도를 한국어 2~3문장"}',
        img)
    if not text:
        return {}
    raw = llm._extract_balanced_json(text) or ""
    return llm._try_parse(raw) or {}


# ---------- 1~3단계: 벤치마킹 분석 ----------

def analyze(topic: str, audience: str, bench: dict) -> dict:
    data = llm.call_json(
        prompts.THUMBNAIL_ANALYZE.format(
            patterns=load_patterns()[:11000],
            bench_title=bench.get("title") or "(없음)",
            bench_copy=bench.get("copy") or "(없음 — 그림·제목에서 추정)",
            bench_image=bench.get("image") or "(없음)",
            bench_url=bench.get("url") or "(없음)",
            topic=topic, audience=audience),
        system=prompts.get_system(), max_tokens=3000,
    )
    if not data.get("structure"):
        raise RuntimeError("벤치마킹 구조분석 실패 (structure 비어 있음)")
    return data


# ---------- 4단계: 디벨롭 ----------

def develop(topic: str, audience: str, analysis: dict, count: int = 4) -> dict:
    data = llm.call_json(
        prompts.THUMBNAIL_DEVELOP.format(
            analysis=json.dumps(analysis, ensure_ascii=False, indent=1),
            topic=topic, audience=audience, count=count),
        system=prompts.get_system(), max_tokens=6000,
    )
    if not data.get("develops"):
        raise RuntimeError("문구 디벨롭 실패 (develops 비어 있음)")
    return data


# ---------- 5~6단계: 키워드 확장 + 검증 ----------

def expand_validate(topic: str, audience: str, analysis: dict, dev: dict,
                    expand_count: int = 3, research: str = "") -> dict:
    research_block = (
        f"[외부 리서치 자료 — 검증 근거로 인용할 것]\n{research[:4000]}"
        if research else
        "[외부 리서치 자료 없음 — 검증 근거에 반드시 '모델 추정'이라고 표기할 것]"
    )
    return llm.call_json(
        prompts.THUMBNAIL_EXPAND.format(
            structure=json.dumps(analysis.get("structure", {}), ensure_ascii=False),
            emotion=json.dumps(analysis.get("emotion", {}), ensure_ascii=False),
            develops=json.dumps({"variable_mapping": dev.get("variable_mapping", ""),
                                 "my_viewer": dev.get("my_viewer", {}),
                                 "develops": dev.get("develops", [])},
                                ensure_ascii=False, indent=1),
            audience=audience, topic=topic,
            expand_count=expand_count, research_block=research_block),
        system=prompts.get_system(), max_tokens=6000,
    )


# ---------- 렌더 (1280×720) ----------

def _css() -> str:
    return """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1280px; height:720px; }
.thumb { width:1280px; height:720px; position:relative; overflow:hidden;
  font-family:'Pretendard','Noto Sans KR',sans-serif; color:#fff; background:#14110f; }
.photo { position:absolute; inset:0; background-size:cover; background-position:center; }
.nophoto { position:absolute; inset:0;
  background:radial-gradient(130% 100% at 75% 20%, #4a4038 0%, #211c18 55%, #100d0b 100%); }
.scrim { position:absolute; inset:0; background:linear-gradient(78deg,
  rgba(0,0,0,.88) 0%, rgba(0,0,0,.62) 34%, rgba(0,0,0,.12) 62%, rgba(0,0,0,0) 80%); }
.chip { position:absolute; top:44px; left:52px; background:#ffd21e; color:#14110f;
  font-weight:800; font-size:34px; letter-spacing:-1px; padding:10px 24px; border-radius:10px; }
.wrap { position:absolute; left:52px; bottom:56px; right:340px; }
.line { font-weight:900; font-size:96px; letter-spacing:-4px; line-height:1.16;
  text-shadow:0 4px 30px rgba(0,0,0,.65); word-break:keep-all; }
.line.small { font-size:80px; }
.hl { color:#ffd21e; }
"""


def _rich(text: str) -> str:
    escaped = _html.escape((text or "").strip()).replace("**", "")
    return re.sub(r"==(.+?)==", r'<span class="hl">\1</span>', escaped)


def thumb_html(pick: dict, bg: str) -> str:
    line1, line2 = (pick.get("line1") or "").strip(), (pick.get("line2") or "").strip()
    if not line1:  # 폴백: copy를 통째로 한 줄에
        line1 = (pick.get("copy") or "").strip()
    # 두 줄이면 글자를 조금 줄여 좌측 안전영역 안에 안정적으로 앉힌다
    size_cls = " small" if line2 and max(len(line1), len(line2)) > 9 else ""
    lines = f'<div class="line{size_cls}">{_rich(line1)}</div>'
    if line2:
        lines += f'<div class="line{size_cls}">{_rich(line2)}</div>'
    label = (pick.get("label") or "").strip()
    chip = f'<div class="chip">{_html.escape(label)}</div>' if label else ""
    photo = (f'<div class="photo" style="background-image:{bg}"></div>'
             if bg else '<div class="nophoto"></div>')
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_css()}</style></head>"
            f"<body><div class='thumb'>{photo}<div class='scrim'></div>{chip}"
            f"<div class='wrap'>{lines}</div></div></body></html>")


def render(picks: list[dict], out: Path, local_imgs: list[str] | None = None,
           prefix: str = "thumb") -> list[Path]:
    """픽별 썸네일을 PNG(원본)+JPG(유튜브 업로드용)로 렌더한다."""
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = str(out / ".imgcache")
    local_imgs = local_imgs or []
    paths: list[Path] = []
    with sync_playwright() as p:
        launch_kw = {"args": ["--no-sandbox"]}
        cpath = chrome_path()
        if cpath:
            launch_kw["executable_path"] = cpath
        browser = p.chromium.launch(**launch_kw)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for i, pick in enumerate(picks, 1):
            # cardnews와 같은 사진 소스 우선순위 (owned → stock → generate → 그라데이션)
            bg = resolve_photo(pick, local_imgs, i - 1, cache_dir)
            page.set_content(thumb_html(pick, bg))
            page.wait_for_timeout(150)
            png = out / f"{prefix}_{i:02d}.png"
            page.screenshot(path=str(png))
            page.screenshot(path=str(out / f"{prefix}_{i:02d}.jpg"), type="jpeg", quality=90)
            paths.append(png)
            log(f"썸네일 {i}/{len(picks)} {pick.get('copy','')[:24]} → {png.name}")
        browser.close()
    return paths


# ---------- 산출물 텍스트 (시트 셀 + md) ----------

def _clean(v) -> str:
    return str(v or "").replace("|", "／").replace("\n", " ").strip()


def emotion_cell(cat: str, score, reason: str) -> str:
    return f"({cat} {score}) {reason}".strip()


def develop_cell(analysis: dict, dev: dict, validation: list[dict] | None = None) -> str:
    """시트 '문구 디벨롭'(N) 셀 텍스트 — 구조분석 + 변주 + 검증."""
    st = analysis.get("structure", {})
    lines = [f"구조: {st.get('copy_structure', '')}"]
    if st.get("title_structure"):
        lines.append(f"(제목: {st['title_structure']})")
    if st.get("caution"):
        lines.append(f"*주의: {st['caution']}")
    if dev.get("variable_mapping"):
        lines.append(f"대입: {dev['variable_mapping']}")
    lines.append("")
    for i, d in enumerate(dev.get("develops", []), 1):
        lines.append(f"{i}. {d.get('copy', '')}")
        if d.get("title"):
            lines.append(f"   ({d['title']})")
    if validation:
        lines += ["", "검증(1~10, 상황/고민/욕구/계획/욕구강도):"]
        for v in validation:
            lines.append(
                f"- {v.get('copy', '')}: {v.get('situation', '')}/{v.get('worry', '')}"
                f"/{v.get('desire', '')}/{v.get('plan', '')}/{v.get('desire_intensity', '')}"
                f" — {v.get('evidence', '')}")
    return "\n".join(lines).strip()


def image_cell(dev: dict) -> str:
    """시트 '이미지 디벨롭'(O) 셀 텍스트 — 감정 카테고리별 그림 아이디어."""
    return "\n".join(
        f"({i.get('category', '')}) {i.get('idea', '')} — {i.get('reason', '')}".strip(" —")
        for i in dev.get("image_ideas", [])).strip()


def build_md(topic: str, audience: str, bench: dict, analysis: dict, dev: dict,
             expand: dict | None = None) -> str:
    """6단계 결과 전체를 시트 붙여넣기 좋은 마크다운으로 만든다."""
    v, e, st = (analysis.get("viewer", {}), analysis.get("emotion", {}),
                analysis.get("structure", {}))
    mv = dev.get("my_viewer", {})
    lines = [
        f"# 썸네일 기획 — {topic}", "",
        f"- 타겟: {audience}",
        f"- 벤치마킹: {_clean(bench.get('copy'))} / 제목: {_clean(bench.get('title'))} {bench.get('url', '')}".rstrip(),
        "", "## 1단계 — 벤치마킹 썸네일을 보는 사람", "",
        "| 상황 | 고민 | 욕구 | 계획 |", "|---|---|---|---|",
        f"| {_clean(v.get('situation'))} | {_clean(v.get('worry'))} | {_clean(v.get('desire'))} | {_clean(v.get('plan'))} |",
        "", "## 2단계 — 감정 배분 (문구+그림=10)", "",
        f"- 문구: **{e.get('copy_category', '')} {e.get('copy_score', '')}** / "
        f"그림: **{e.get('image_category', '')} {e.get('image_score', '')}**",
        f"- {_clean(e.get('reason'))}",
        "", "## 3단계 — 문구+제목 세트 구조분석", "",
        f"- 문구 구조: {_clean(st.get('copy_structure'))}",
        f"- 제목 구조: {_clean(st.get('title_structure'))}",
        f"- 주의할 점: {_clean(st.get('caution'))}",
        f"- 욕구 매핑: {_clean(analysis.get('desire_mapping'))}",
        "", f"## 4단계 — 디벨롭 ({_clean(dev.get('variable_mapping'))})", "",
        "내 키워드 시청자:", "",
        "| 상황 | 고민 | 욕구 | 계획 |", "|---|---|---|---|",
        f"| {_clean(mv.get('situation'))} | {_clean(mv.get('worry'))} | {_clean(mv.get('desire'))} | {_clean(mv.get('plan'))} |",
        "", "| # | 썸네일 문구 | 영상 제목 | 감정 증폭 포인트 |", "|---|---|---|---|",
    ]
    for i, d in enumerate(dev.get("develops", []), 1):
        lines.append(f"| {i} | {_clean(d.get('copy'))} | {_clean(d.get('title'))} | {_clean(d.get('note'))} |")
    lines += ["", "### 이미지 디벨롭", ""]
    for i in dev.get("image_ideas", []):
        lines.append(f"- ({_clean(i.get('category'))}) {_clean(i.get('idea'))} — {_clean(i.get('reason'))}")
    if expand:
        lines += ["", "## 5단계 — 키워드 확장", ""]
        for x in expand.get("expansions", []):
            lines.append(f"### {_clean(x.get('keyword'))} — {_clean(x.get('why'))}")
            for d in x.get("develops", []):
                lines.append(f"- {_clean(d.get('copy'))} ({_clean(d.get('title'))})")
            lines.append("")
        vals = expand.get("validation", [])
        if vals:
            lines += ["## 6단계 — 검증 (상황/고민/욕구/계획/욕구강도, 1~10)", "",
                      "| 키워드 | 문구 | 상황 | 고민 | 욕구 | 계획 | 강도 | 근거 |",
                      "|---|---|---|---|---|---|---|---|"]
            for vv in vals:
                lines.append(
                    f"| {_clean(vv.get('keyword'))} | {_clean(vv.get('copy'))} | {vv.get('situation', '')} "
                    f"| {vv.get('worry', '')} | {vv.get('desire', '')} | {vv.get('plan', '')} "
                    f"| {vv.get('desire_intensity', '')} | {_clean(vv.get('evidence'))} |")
    return "\n".join(lines) + "\n"


def save_to_review(topic: str, md_body: str) -> str:
    """볼트 05 리뷰/대기에 저장 → script_feedback이 텔레그램 알림·답장 핑퐁을 잇는다."""
    import os
    from vault_pipeline.vault_io import now_kst, vault_root
    rel = os.getenv("VAULT_SCRIPT_PATH", REVIEW_DIR_DEFAULT).strip("/")
    folder = vault_root() / rel
    folder.mkdir(parents=True, exist_ok=True)
    date = now_kst().strftime("%Y-%m-%d")
    fm = "\n".join([
        "---",
        "type: thumbnail",
        "상태: 초안",
        f"생성일: {date}",
        "채널: youtube",
        f"카테고리: {topic}",
        "검수상태: 대기",
        "generator: dreamgrow-orchestrator",
        "---",
    ])
    name = f"썸네일_{_file_token(topic)[:40] or '무제'}.md"
    path = folder / name
    n = 1
    while path.exists():
        n += 1
        path = folder / f"{name[:-3]}-{n}.md"
    path.write_text(f"{fm}\n\n{md_body}", encoding="utf-8")
    return path.name


# ---------- 한 건 실행 (수동/시트 공용) ----------

def run_one(topic: str, audience: str, bench: dict, expand_count: int,
            out: Path, local_imgs: list[str], pick_count: int = 4,
            save_vault: bool = True) -> dict:
    log(f"1~3단계 벤치마킹 분석: {bench.get('copy') or bench.get('title') or bench.get('url', '')}")
    analysis = analyze(topic, audience, bench)
    e = analysis.get("emotion", {})
    log(f"  감정: 문구 {e.get('copy_category')} {e.get('copy_score')}"
        f" + 그림 {e.get('image_category')} {e.get('image_score')}")
    log(f"  구조: {analysis.get('structure', {}).get('copy_structure', '')[:60]}")

    log(f"4단계 디벨롭: {topic}")
    dev = develop(topic, audience, analysis, pick_count)
    for d in dev.get("develops", [])[:5]:
        log(f"  - {d.get('copy', '')}")

    expand = None
    if expand_count > 0:
        log(f"5~6단계 키워드 확장({expand_count}개) + 검증")
        expand = expand_validate(topic, audience, analysis, dev, expand_count)

    picks = dev.get("picks", [])[:pick_count]
    if picks:
        log("렌더 (1280×720)")
        render(picks, out, local_imgs, prefix=f"thumb_{_file_token(topic)[:16] or 'x'}")

    md = build_md(topic, audience, bench, analysis, dev, expand)
    (out / f"썸네일_{_file_token(topic)[:40] or '무제'}.md").write_text(md, encoding="utf-8")
    (out / "thumbnail_plan.json").write_text(
        json.dumps({"topic": topic, "bench": bench, "analysis": analysis,
                    "develop": dev, "expand": expand}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    if save_vault:
        name = save_to_review(topic, md)
        log(f"볼트 저장: 05 리뷰/대기/{name}")
    return {"analysis": analysis, "develop": dev, "expand": expand}


# ---------- 시트 모드 ----------

def find_pending(rows: list[list[str]]) -> list[int]:
    """처리할 행 인덱스(0-base, 데이터 기준): K(키워드) 있고 N(문구 디벨롭) 비어 있고
    벤치마크 단서(B URL / D 제목)가 하나라도 있는 행."""
    todo = []
    for i, row in enumerate(rows):
        def cell(c):
            return (row[c].strip() if c < len(row) and row[c] else "")
        if not cell(COL["my_keyword"]) or cell(COL["copy_develop"]):
            continue
        if cell(COL["url"]) or cell(COL["title"]):
            todo.append(i)
    return todo


def _row_updates(row: list[str], result: dict, bench: dict) -> dict[str, str]:
    """빈 칸만 채우는 {열문자: 값} 목록을 만든다."""
    analysis, dev = result["analysis"], result["develop"]
    v, e = analysis.get("viewer", {}), analysis.get("emotion", {})
    validation = (result.get("expand") or {}).get("validation", [])

    def empty(c):
        return not (c < len(row) and (row[c] or "").strip())

    upd: dict[str, str] = {}
    for col_idx, letter, value in (
        (COL["situation"], "E", v.get("situation", "")),
        (COL["worry"], "F", v.get("worry", "")),
        (COL["desire"], "G", v.get("desire", "")),
        (COL["plan"], "H", v.get("plan", "")),
        (COL["copy_emotion"], "I",
         emotion_cell(e.get("copy_category", ""), e.get("copy_score", ""),
                      f"{bench.get('copy', '')} — {e.get('reason', '')}")),
        (COL["image_emotion"], "J",
         emotion_cell(e.get("image_category", ""), e.get("image_score", ""),
                      bench.get("image", ""))),
        (COL["copy_develop"], "N", develop_cell(analysis, dev, validation)),
        (COL["image_develop"], "O", image_cell(dev)),
        (COL["made_title"], "Q",
         "\n".join(p.get("title", "") for p in dev.get("picks", []) if p.get("title"))),
    ):
        if value and empty(col_idx):
            upd[letter] = value
    return upd


def expansion_rows(expand: dict, date: str) -> list[list[str]]:
    """5단계 확장 키워드를 시트 새 행(A~Q)으로 만든다."""
    out_rows = []
    vals = {v.get("keyword", ""): v for v in expand.get("validation", [])}
    for x in expand.get("expansions", []):
        kw = x.get("keyword", "")
        dev_lines = [f"({x.get('why', '')})", ""]
        dev_lines += [f"{i}. {d.get('copy', '')}\n   ({d.get('title', '')})"
                      for i, d in enumerate(x.get("develops", []), 1)]
        vv = vals.get(kw)
        if vv:
            dev_lines += ["", f"검증: 상황{vv.get('situation', '')}/고민{vv.get('worry', '')}"
                              f"/욕구{vv.get('desire', '')}/계획{vv.get('plan', '')}"
                              f"/강도{vv.get('desire_intensity', '')} — {vv.get('evidence', '')}"]
        viewer = x.get("viewer", {})
        row = [""] * 17  # A~Q
        row[COL["date_kw"]] = f"{date} {kw} (자동 확장)"
        row[COL["situation"]] = viewer.get("situation", "")
        row[COL["worry"]] = viewer.get("worry", "")
        row[COL["desire"]] = viewer.get("desire", "")
        row[COL["plan"]] = viewer.get("plan", "")
        row[COL["my_keyword"]] = kw
        row[COL["copy_develop"]] = "\n".join(dev_lines).strip()
        out_rows.append(row)
    return out_rows


def run_sheet(audience: str, expand_count: int, out: Path,
              local_imgs: list[str], max_rows: int = 3, save_vault: bool = True):
    """시트에서 대기 행을 찾아 처리하고 결과를 되써넣는다."""
    from vault_pipeline.vault_io import now_kst
    if not gsheet.available():
        log("GSHEET_SA_JSON 미설정 — 시트 모드를 건너뜁니다 (서비스 계정 키 필요)")
        return
    title = gsheet.resolve_title()
    rows = gsheet.read(f"A2:{LAST_COL}1000", title)
    todo = find_pending(rows)
    if not todo:
        log("처리할 행 없음 (K 키워드 있고 N 문구 디벨롭 빈 행이 없음)")
        return
    log(f"대기 행 {len(todo)}개 → 최대 {max_rows}개 처리")
    for i in todo[:max_rows]:
        row = rows[i]
        rownum = i + 2  # 헤더 1행 + 1-base

        def cell(c):
            return (row[c].strip() if c < len(row) and row[c] else "")

        topic = cell(COL["my_keyword"])
        bench = {"url": cell(COL["url"]), "title": cell(COL["title"])}
        ocr = ocr_benchmark(bench["url"]) if bench["url"] else {}
        bench["copy"] = ocr.get("copy", "")
        bench["image"] = ocr.get("image", "")
        if not bench["copy"]:
            log(f"  행{rownum}: 썸네일 OCR 불가 — 제목·기존 분석 텍스트로 진행")
            bench["copy"] = ""
            bench["image"] = bench.get("image") or cell(COL["image_emotion"])
        log(f"행{rownum} 처리: 키워드={topic}")
        result = run_one(topic, audience, bench, expand_count, out, local_imgs,
                         save_vault=save_vault)
        for letter, value in _row_updates(row, result, bench).items():
            gsheet.update(f"{letter}{rownum}", [[value]], title)
        log(f"  행{rownum} 시트 기록 완료")
        expand = result.get("expand")
        if expand and expand.get("expansions"):
            new_rows = expansion_rows(expand, now_kst().strftime("%Y-%m-%d"))
            if new_rows:
                gsheet.append(f"A2:{LAST_COL}", new_rows, title)
                log(f"  확장 키워드 {len(new_rows)}행 추가")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true",
                    help="구글 시트에서 대기 행을 찾아 처리하고 되써넣기 (GSHEET_SA_JSON 필요)")
    ap.add_argument("--topic", default="", help="내가 만들 영상 키워드 (수동 모드)")
    ap.add_argument("--audience", default="초등 저학년 학부모")
    ap.add_argument("--benchmark-copy", default="", help="벤치마킹 썸네일 문구")
    ap.add_argument("--benchmark-title", default="", help="벤치마킹 영상 제목")
    ap.add_argument("--benchmark-image", default="", help="벤치마킹 썸네일 그림 묘사")
    ap.add_argument("--benchmark-url", default="", help="벤치마킹 영상 URL (있으면 비전 OCR 시도)")
    ap.add_argument("--expand", type=int, default=3, help="5단계 확장 키워드 수 (0=생략)")
    ap.add_argument("--max-rows", type=int, default=3, help="시트 모드에서 한 번에 처리할 행 수")
    ap.add_argument("--photos-dir", default="", help="소유 사진 폴더 (배경 1순위)")
    ap.add_argument("--out", default="thumbnail_out")
    ap.add_argument("--no-vault", action="store_true", help="볼트 05 리뷰/대기 저장 생략")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ensure_fonts()
    local_imgs = []
    if args.photos_dir:
        import glob as _glob
        local_imgs = sorted(g for ext in ("jpg", "jpeg", "png", "webp")
                            for g in _glob.glob(str(Path(args.photos_dir) / f"*.{ext}")))
        log(f"로컬 사진 {len(local_imgs)}장 사용")

    if args.sheet:
        run_sheet(args.audience, args.expand, out, local_imgs,
                  max_rows=args.max_rows, save_vault=not args.no_vault)
    else:
        if not args.topic:
            ap.error("--topic 또는 --sheet 중 하나는 필요합니다")
        bench = {"copy": args.benchmark_copy, "title": args.benchmark_title,
                 "image": args.benchmark_image, "url": args.benchmark_url}
        if args.benchmark_url and not bench["copy"]:
            ocr = ocr_benchmark(args.benchmark_url)
            bench["copy"] = ocr.get("copy", "")
            bench["image"] = bench["image"] or ocr.get("image", "")
        run_one(args.topic, args.audience, bench, args.expand, out, local_imgs,
                save_vault=not args.no_vault)
    log(f"완료 → {out.resolve()}")


if __name__ == "__main__":
    main()
