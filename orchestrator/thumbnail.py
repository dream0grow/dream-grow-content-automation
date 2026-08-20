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
from orchestrator.cardnews import _file_to_bg, chrome_path, ensure_fonts, resolve_photo

W, H = 1280, 720
# 셀 상태색: 노랑 = 사람 컨펌 완료(사람이 칠함), 파랑 = 작업(렌더) 완료(파이프라인이 칠함)
DONE_BLUE = (0.788, 0.854, 0.973)  # #c9daf8

# ── 사용자 확정 렌더 스타일 (2026-08-19 확정 — 이 크기를 기억하고 유지할 것) ──
LINE_PX = 112          # 하단 2줄 본문 문구 크기 (벤치마크 "같은 책을 3번 읽으면" 급)
LINE_PX_SMALL = 96     # 한 줄 12자 초과 시 축소 크기
KICKER_PX = 46         # 좌상단 킥커("현직 초등 교사가 알려주는") 크기
KICKER_COLOR = "#a8e063"  # 킥커 연두색 (벤치마크 "뇌과학이 알려주는" 톤)
KICKER_DEFAULT = "현직 초등 교사가 알려주는"  # env DG_THUMB_KICKER로 변경 가능

# v2 스타일 (가독성 비교용): 검은고딕(Black Han Sans) 중앙 정렬, 1줄 흰색·2줄 노란색,
# 두꺼운 검은 외곽선 — 벤치마크 "공부, 게임, 운동 / 남보다 못하는 이유" 톤
V2_LINE_PX = 118
V2_LINE_PX_SMALL = 100
V2_YELLOW = "#ffd400"

# 실제 사람 피부처럼 — 사용자 지정 리얼리즘 프롬프트 (확정 렌더의 photo_prompt에 항상 덧붙임)
REALISM = ("visible pores, skin texture, fine wrinkles, slight skin imperfections, "
           "vellus hair, peach fuzz, natural skin blemishes, slight freckles, no makeup, "
           "candid shot, snapshot, unfiltered, amateur photography, natural daylight, "
           "soft ambient light, shot on 35mm lens, iPhone photo")

# 참조 이미지(실제 책 표지 등): data/thumbnail_assets/<키워드(공백 제거)>/ 에 넣으면
# 확정 렌더가 그 이미지를 참조해 장면을 생성한다 (gpt-image-1 edits / Gemini 이미지 입력)
ASSETS_DIR = Path(__file__).resolve().parent.parent / "data" / "thumbnail_assets"
PATTERNS_FILE = Path(__file__).resolve().parent.parent / "data" / "thumbnail_patterns.md"
# 원고 핑퐁과 같은 폴더 — script_feedback이 `검수상태: 대기` + 최근 생성일이면 알림을 보낸다
REVIEW_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"

# 분석 탭 기본 열 배치 (2026-08-19 개편: J 영상 문구 분석 신설, M 키워드 디벨롭,
# P 핫비디오 디벨롭). 실행 시 헤더 행을 읽어 이름으로 재해석하므로(resolve_columns)
# 열이 옮겨져도 따라간다 — 여기 값은 헤더를 못 읽었을 때의 폴백이다.
COL_DEFAULT = {"date_kw": 0, "url": 1, "thumb_img": 2, "title": 3,
               "situation": 4, "worry": 5, "desire": 6, "plan": 7,        # E~H
               "copy_emotion": 8, "structure": 9, "image_emotion": 10,    # I,J,K
               "my_keyword": 11, "kw_develop": 12,                        # L,M
               "hot_thumb": 13, "hot_analysis": 14, "hot_develop": 15,    # N,O,P
               "image_develop": 16, "made_thumb": 17, "made_title": 18}   # Q,R,S
LAST_COL = "S"

# 헤더 이름 → 열 키 매핑 (공백 제거 후 startswith 비교, 위에서부터 우선)
_HEADER_PATTERNS = [
    ("hot_analysis", "핫비디오썸네일분석"),
    ("hot_develop", "핫비디오로문구디벨롭"),
    ("hot_thumb", "핫비디오썸네일"),
    ("kw_develop", "키워드로문구디벨롭"),
    ("kw_develop", "문구디벨롭"),
    ("structure", "영상문구분석"),
    ("copy_emotion", "썸네일문구"),
    ("image_develop", "이미지디벨롭"),
    ("image_emotion", "그림"),
    ("my_keyword", "내가만들"),
    ("made_thumb", "만든썸네일"),
    ("made_title", "만든제목"),
    ("thumb_img", "썸네일이미지"),
    ("title", "영상제목"),
    ("url", "영상URL"),
    ("date_kw", "날짜"),
    ("situation", "상황"), ("worry", "고민"), ("desire", "욕구"), ("plan", "계획"),
]


def resolve_columns(header: list[str]) -> dict[str, int]:
    """헤더 행에서 열 이름을 찾아 {키: 인덱스}를 만든다. 못 찾은 키는 기본값."""
    cols = dict(COL_DEFAULT)
    found: set[str] = set()
    for idx, cell in enumerate(header):
        name = re.sub(r"\s+", "", str(cell or ""))
        if not name:
            continue
        for key, pat in _HEADER_PATTERNS:
            if key not in found and name.startswith(pat):
                cols[key] = idx
                found.add(key)
                break
    return cols


def col_letter(idx: int) -> str:
    """0-base 열 인덱스 → A1 열 문자 (0→A, 18→S)."""
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def log(msg: str):
    print(f"[thumbnail] {msg}", flush=True)


def ensure_blackhansans():
    """검은고딕(Black Han Sans — v2 스타일)이 없으면 받아 설치한다."""
    import subprocess
    import urllib.request
    try:
        out = subprocess.run(["fc-list"], capture_output=True, text=True, timeout=20).stdout
        if "Black Han Sans" in out:
            return
    except Exception:
        pass
    dest = Path("/usr/share/fonts/blackhansans")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        fp = dest / "BlackHanSans-Regular.ttf"
        if not fp.exists():
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/google/fonts/main/ofl/blackhansans/BlackHanSans-Regular.ttf",
                fp)
        subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=60)
        log("검은고딕(Black Han Sans) 폰트 설치 완료")
    except Exception as e:
        log(f"검은고딕 설치 실패(도현체로 진행): {e}")


def ensure_dohyeon():
    """배달의민족 도현체(구글 폰트 'Do Hyeon')가 없으면 받아 설치한다."""
    import subprocess
    import urllib.request
    try:
        out = subprocess.run(["fc-list"], capture_output=True, text=True, timeout=20).stdout
        if "Do Hyeon" in out or "DoHyeon" in out:
            return
    except Exception:
        pass
    dest = Path("/usr/share/fonts/dohyeon")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        fp = dest / "DoHyeon-Regular.ttf"
        if not fp.exists():
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/google/fonts/main/ofl/dohyeon/DoHyeon-Regular.ttf",
                fp)
        subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=60)
        log("도현체(Do Hyeon) 폰트 설치 완료")
    except Exception as e:
        log(f"도현체 설치 실패(Pretendard로 진행): {e}")


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
.scrim { position:absolute; inset:0; background:linear-gradient(to top,
  rgba(0,0,0,.94) 0%, rgba(0,0,0,.80) 20%, rgba(0,0,0,.35) 46%, rgba(0,0,0,0) 62%); }
.wrap { position:absolute; left:52px; bottom:44px; right:60px; }
.kicker { font-family:'Do Hyeon','BM DoHyeon','Pretendard','Noto Sans KR',sans-serif;
  font-size:KICKER_PXpx; color:KICKER_COLOR; margin-bottom:14px;
  -webkit-text-stroke:1.5px currentColor; paint-order:stroke fill;
  text-shadow:0 3px 18px rgba(0,0,0,.7); }
.line { font-family:'Do Hyeon','BM DoHyeon','Pretendard','Noto Sans KR',sans-serif;
  font-weight:900; font-size:LINE_PXpx; letter-spacing:-2px; line-height:1.14;
  -webkit-text-stroke:3px currentColor; paint-order:stroke fill;  /* 도현체 단일 굵기 → 강제 진하게 */
  text-shadow:0 4px 30px rgba(0,0,0,.7); word-break:keep-all; }
.line.small { font-size:LINE_PX_SMALLpx; }
.hl { color:#ffd21e; }
.wrapv2 { position:absolute; left:36px; right:36px; bottom:28px; text-align:center; }
.linev2 { font-family:'Black Han Sans','Do Hyeon','Pretendard','Noto Sans KR',sans-serif;
  font-size:V2_LINE_PXpx; color:#fff; letter-spacing:0; line-height:1.18;
  -webkit-text-stroke:9px #000; paint-order:stroke fill; word-break:keep-all; }
.linev2.small { font-size:V2_LINE_PX_SMALLpx; }
.linev2.yellow { color:V2_YELLOW; }
""".replace("KICKER_PX", str(KICKER_PX)).replace("KICKER_COLOR", KICKER_COLOR) \
   .replace("V2_LINE_PX_SMALL", str(V2_LINE_PX_SMALL)).replace("V2_LINE_PX", str(V2_LINE_PX)) \
   .replace("V2_YELLOW", V2_YELLOW) \
   .replace("LINE_PX_SMALL", str(LINE_PX_SMALL)).replace("LINE_PX", str(LINE_PX))


def _rich(text: str) -> str:
    escaped = _html.escape((text or "").strip()).replace("**", "")
    return re.sub(r"==(.+?)==", r'<span class="hl">\1</span>', escaped)


def thumb_html(pick: dict, bg: str) -> str:
    line1, line2 = (pick.get("line1") or "").strip(), (pick.get("line2") or "").strip()
    if not line1:  # 폴백: copy를 통째로 한 줄에
        line1 = (pick.get("copy") or "").strip()
    photo_div = (f'<div class="photo" style="background-image:{bg}"></div>'
                 if bg else '<div class="nophoto"></div>')
    if (pick.get("style") or "").strip() == "v2":
        # v2: 검은고딕 중앙 정렬, 1줄 흰색 + 2줄 노란색 전체, 두꺼운 검은 외곽선 (킥커 없음)
        def plain(t):
            return re.sub(r"==(.+?)==", r"\1", (t or "").strip()).replace("**", "")
        p1, p2 = plain(line1), plain(line2)
        size_cls = " small" if max(len(p1), len(p2)) > 11 else ""
        lines = f'<div class="linev2{size_cls}">{_html.escape(p1)}</div>'
        if p2:
            lines += f'<div class="linev2 yellow{size_cls}">{_html.escape(p2)}</div>'
        return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_css()}</style>"
                f"</head><body><div class='thumb'>{photo_div}<div class='scrim'></div>"
                f"<div class='wrapv2'>{lines}</div></div></body></html>")
    # 긴 줄은 한 단계 줄여 화면 폭 안에 앉힌다 (확정 크기: LINE_PX/LINE_PX_SMALL)
    size_cls = " small" if max(len(line1), len(line2)) > 12 else ""
    lines = f'<div class="line{size_cls}">{_rich(line1)}</div>'
    if line2:
        lines += f'<div class="line{size_cls}">{_rich(line2)}</div>'
    label = (pick.get("label") or "").strip()
    kicker = f'<div class="kicker">{_html.escape(label)}</div>' if label else ""
    photo = (f'<div class="photo" style="background-image:{bg}"></div>'
             if bg else '<div class="nophoto"></div>')
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_css()}</style></head>"
            f"<body><div class='thumb'>{photo}<div class='scrim'></div>"
            f"<div class='wrap'>{kicker}{lines}</div></div></body></html>")


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
            if pick.get("_bg_file"):  # 참조 이미지 편집 등으로 이미 만든 배경
                bg = _file_to_bg(pick["_bg_file"])
            else:  # cardnews와 같은 사진 소스 우선순위 (owned → stock → generate → 그라데이션)
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


def structure_cell(analysis: dict) -> str:
    """시트 '영상 문구 분석'(J) 셀 텍스트 — 문구+제목 세트 구조분석."""
    st = analysis.get("structure", {})
    lines = [f"구조 : {st.get('copy_structure', '')}"]
    if st.get("title_structure"):
        lines.append(f"(제목: {st['title_structure']})")
    if st.get("caution"):
        lines.append(f"*주의: {st['caution']}")
    return "\n".join(lines).strip()


def develop_cell(dev: dict, validation: list[dict] | None = None) -> str:
    """시트 '키워드로 문구 디벨롭'(M) 셀 텍스트 — 대입 선언 + 변주 + 검증.

    구조분석은 J열(structure_cell)에 따로 들어가므로 여기선 반복하지 않는다.
    """
    lines = []
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


def hot_develop_cell(hot: dict) -> str:
    """시트 '핫비디오로 문구 디벨롭'(P) 셀 텍스트 — 핫비디오 구조 + 같은 주제 변주."""
    lines = []
    if hot.get("hot_structure"):
        lines += [f"핫비디오 구조 : {hot['hot_structure']}", ""]
    for i, d in enumerate(hot.get("develops", []), 1):
        lines.append(f"{i}. {d.get('copy', '')}")
        if d.get("title"):
            lines.append(f"   ({d['title']})")
        if d.get("note"):
            lines.append(f"   → {d['note']}")
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


# ---------- 렌더 확정 (색칠 = 수정·확인 완료 신호) ----------

def parse_made_title(text: str) -> tuple[str, str]:
    """S열 '만든 제목' 텍스트 → (썸네일 문구, 영상 제목).

    관례: 문구 다음 줄에 괄호로 제목. 예)
      "고전을 만화책처럼 읽는 법\\n(이 방법으로 읽으니 아이가 고전을 다 읽었습니다)"
    괄호가 없으면 전체를 문구로, 제목은 빈 문자열.
    """
    text = (text or "").strip()
    m = re.search(r"\(([^()]+)\)\s*$", text, re.S)
    if m:
        title = " ".join(m.group(1).split())
        copy = " ".join(text[:m.start()].split())
        return copy, title
    return " ".join(text.split()), ""


def render_spec(topic: str, copy: str, title: str, image_direction: str) -> dict:
    """확정 문구·이미지 지시 → 렌더 사양(두 줄 분할·강조·칩·사진 지시)."""
    spec = llm.call_json(
        prompts.THUMBNAIL_RENDER_SPEC.format(
            topic=topic, copy=copy, title=title or "(없음)",
            image_direction=image_direction or "(없음 — 문구에 맞는 장면을 보수적으로)"),
        system=prompts.get_system(), max_tokens=1500)
    spec.setdefault("copy", copy)
    spec.setdefault("title", title)
    if not spec.get("line1"):
        spec["line1"] = copy
    return spec


def find_render_ready(rows: list[list[str]], cols: dict[str, int],
                      bgs: list[list]) -> list[int]:
    """렌더 대상: Q(이미지 디벨롭)·S(만든 제목) 둘 다 색칠됐고 R(만든 썸네일) 빈 행.

    bgs는 데이터 행 기준(rows와 같은 인덱스)의 배경색 2차원 리스트 —
    각 행에서 [이미지 디벨롭, 만든 제목] 순서 2칸.
    """
    ready = []
    for i, row in enumerate(rows):
        if _cell(row, cols["made_thumb"]) or not _cell(row, cols["made_title"]):
            continue
        bg_row = bgs[i] if i < len(bgs) else []
        q_bg = bg_row[0] if len(bg_row) > 0 else None
        s_bg = bg_row[1] if len(bg_row) > 1 else None
        if gsheet.is_colored(q_bg) and gsheet.is_colored(s_bg):
            ready.append(i)
        elif gsheet.is_colored(q_bg) or gsheet.is_colored(s_bg):
            log(f"  행{i + 2}: 이미지 디벨롭/만든 제목 중 한쪽만 색칠 — 둘 다 칠해지면 렌더")
    return ready


def find_assets(topic: str) -> list[str]:
    """키워드의 참조 이미지들(실제 책 표지 등)을 찾는다.

    ① data/thumbnail_assets/<키워드>/ 폴더 안 이미지
    ② data/thumbnail_assets/<키워드>*.jpg 처럼 폴더 없이 낱개로 올린 파일
    (GitHub 웹 업로드는 폴더 만들기가 번거로워 둘 다 인식한다)
    """
    import unicodedata

    def nfc(s: str) -> str:
        # 맥/GitHub 웹 업로드 파일명은 NFD(자모 분해)로 올 수 있다 → NFC로 맞춰 비교
        return unicodedata.normalize("NFC", s)

    token = nfc(_file_token(topic)[:40] or "무제")
    exts = (".jpg", ".jpeg", ".png", ".webp")
    hits: list[str] = []
    if ASSETS_DIR.is_dir():
        for p in ASSETS_DIR.iterdir():
            if p.is_dir() and nfc(p.name) == token:
                hits += [str(f) for f in p.iterdir() if f.suffix.lower() in exts]
            elif p.is_file() and p.suffix.lower() in exts and nfc(p.stem).startswith(token):
                hits.append(str(p))
    return sorted(set(hits))


def save_render_to_vault(topic: str, png: Path, jpg: Path) -> str:
    """렌더 결과를 볼트 파이프라인/썸네일/에 저장하고 상대 경로(png)를 반환."""
    from vault_pipeline.vault_io import now_kst, vault_root
    folder = vault_root() / "파이프라인" / "썸네일"
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{now_kst().strftime('%Y%m%d')}_{_file_token(topic)[:30] or '무제'}"
    n, name = 0, stem
    while (folder / f"{name}.png").exists():
        n += 1
        name = f"{stem}-{n}"
    (folder / f"{name}.png").write_bytes(png.read_bytes())
    (folder / f"{name}.jpg").write_bytes(jpg.read_bytes())
    return f"파이프라인/썸네일/{name}.png"


# ---------- 시트 모드 ----------

def _cell(row: list[str], c: int) -> str:
    return (str(row[c]).strip() if c < len(row) and row[c] else "")


def find_pending(rows: list[list[str]], cols: dict[str, int]) -> list[int]:
    """전체 처리 대상(0-base): L(키워드) 있고 M(키워드로 문구 디벨롭) 비어 있고
    벤치마크 단서(B URL / D 제목)가 하나라도 있는 행."""
    todo = []
    for i, row in enumerate(rows):
        if not _cell(row, cols["my_keyword"]) or _cell(row, cols["kw_develop"]):
            continue
        if _cell(row, cols["url"]) or _cell(row, cols["title"]):
            todo.append(i)
    return todo


def find_structure_backfill(rows: list[list[str]], cols: dict[str, int],
                            skip: set[int]) -> list[int]:
    """J(영상 문구 분석) 백필 대상: J 비어 있고 단서(I 문구 분석 / D 제목) 있는 행.
    바로 위 행과 같은 영상(URL+제목)인 묶임 행은 건너뛴다."""
    todo = []
    prev_key = None
    for i, row in enumerate(rows):
        key = (_cell(row, cols["url"]), _cell(row, cols["title"]))
        dup = key != ("", "") and key == prev_key
        prev_key = key if key != ("", "") else prev_key
        if i in skip or dup:
            continue
        if _cell(row, cols["structure"]):
            continue
        if _cell(row, cols["copy_emotion"]) or _cell(row, cols["title"]):
            todo.append(i)
    return todo


def hot_video_develop(topic: str, row: list[str], cols: dict[str, int],
                      analysis_hint: dict | None = None) -> dict | None:
    """5) 주제는 그대로, 문구 구조를 핫비디오 것으로 — P열 텍스트용 결과. 재료 없으면 None."""
    hot_thumb = _cell(row, cols["hot_thumb"])
    hot_analysis = _cell(row, cols["hot_analysis"])
    hot_copy = ""
    if hot_thumb.startswith("http"):
        hot_copy = (ocr_benchmark(hot_thumb) or {}).get("copy", "")
    elif hot_thumb:
        hot_copy = hot_thumb  # 문구를 직접 적어둔 경우
    if not (hot_copy or hot_analysis):
        return None
    viewer = (analysis_hint or {}).get("viewer", {})
    data = llm.call_json(
        prompts.THUMBNAIL_HOTVIDEO.format(
            topic=topic,
            situation=viewer.get("situation") or _cell(row, cols["situation"]),
            worry=viewer.get("worry") or _cell(row, cols["worry"]),
            desire=viewer.get("desire") or _cell(row, cols["desire"]),
            plan=viewer.get("plan") or _cell(row, cols["plan"]),
            copy_emotion=_cell(row, cols["copy_emotion"]),
            hot_copy=hot_copy or "(없음 — 분석 메모에서 추정)",
            hot_analysis=hot_analysis or "(없음)"),
        system=prompts.get_system(), max_tokens=4000)
    return data if data.get("develops") else None


def _row_updates(row: list[str], cols: dict[str, int], result: dict,
                 bench: dict, hot: dict | None = None) -> dict[str, str]:
    """빈 칸만 채우는 {열문자: 값} 목록을 만든다."""
    analysis, dev = result["analysis"], result["develop"]
    v, e = analysis.get("viewer", {}), analysis.get("emotion", {})
    validation = (result.get("expand") or {}).get("validation", [])

    items = [
        ("situation", v.get("situation", "")),
        ("worry", v.get("worry", "")),
        ("desire", v.get("desire", "")),
        ("plan", v.get("plan", "")),
        ("copy_emotion", emotion_cell(e.get("copy_category", ""), e.get("copy_score", ""),
                                      f"{bench.get('copy', '')} — {e.get('reason', '')}")),
        ("structure", structure_cell(analysis)),
        ("image_emotion", emotion_cell(e.get("image_category", ""), e.get("image_score", ""),
                                       bench.get("image", ""))),
        ("kw_develop", develop_cell(dev, validation)),
        ("image_develop", image_cell(dev)),
        ("made_title", "\n".join(p.get("title", "") for p in dev.get("picks", [])
                                 if p.get("title"))),
    ]
    if hot:
        items.append(("hot_develop", hot_develop_cell(hot)))
    upd: dict[str, str] = {}
    for key, value in items:
        if value and not _cell(row, cols[key]):
            upd[col_letter(cols[key])] = value
    return upd


def expansion_values(expand: dict, parent_row: list[str],
                     cols: dict[str, int]) -> list[list[str]]:
    """5단계 확장 키워드를 벤치마크 '하위 행' 값으로 만든다 (A~M 범위).

    연습 시트 방식대로 벤치마크 정보(A,B,D,E~K)를 물려받고,
    L에 새 키워드, M에 그 키워드의 문구 디벨롭(+검증)을 담는다.
    """
    out_rows = []
    vals = {v.get("keyword", ""): v for v in expand.get("validation", [])}
    width = max(cols["kw_develop"], cols["my_keyword"]) + 1
    for x in expand.get("expansions", []):
        kw = x.get("keyword", "")
        dev_lines = [f"(자동 확장 — {x.get('why', '')})", ""]
        dev_lines += [f"{i}. {d.get('copy', '')}\n   ({d.get('title', '')})"
                      for i, d in enumerate(x.get("develops", []), 1)]
        vv = vals.get(kw)
        if vv:
            dev_lines += ["", f"검증: 상황{vv.get('situation', '')}/고민{vv.get('worry', '')}"
                              f"/욕구{vv.get('desire', '')}/계획{vv.get('plan', '')}"
                              f"/강도{vv.get('desire_intensity', '')} — {vv.get('evidence', '')}"]
        row = [""] * width
        # 벤치마크 정보 상속 (C 썸네일 이미지는 셀 위 이미지라 API로 복사 불가)
        for key in ("date_kw", "url", "title", "situation", "worry", "desire", "plan",
                    "copy_emotion", "structure", "image_emotion"):
            if cols[key] < width:
                row[cols[key]] = _cell(parent_row, cols[key])
        viewer = x.get("viewer", {})
        for key, val in (("situation", viewer.get("situation")),
                         ("worry", viewer.get("worry")),
                         ("desire", viewer.get("desire")),
                         ("plan", viewer.get("plan"))):
            if val:  # 확장 키워드의 시청자 분석이 있으면 그걸 우선
                row[cols[key]] = val
        row[cols["my_keyword"]] = kw
        row[cols["kw_develop"]] = "\n".join(dev_lines).strip()
        out_rows.append(row)
    return out_rows


def insert_expansions(rownum: int, values: list[list[str]], sheet_title: str):
    """벤치마크 행(rownum) 바로 아래에 확장 행을 삽입하고 그룹으로 묶는다."""
    n = len(values)
    gsheet.insert_rows(rownum, n)
    width = max(len(v) for v in values)
    gsheet.update(f"A{rownum + 1}:{col_letter(width - 1)}{rownum + n}", values, sheet_title)
    gsheet.group_rows(rownum + 1, rownum + n)


def run_sheet(audience: str, expand_count: int, out: Path,
              local_imgs: list[str], max_rows: int = 3, save_vault: bool = True,
              backfill_max: int = 8):
    """시트를 읽어 ①J 구조분석 백필 ②대기 행 전체 처리(하위 확장 행 삽입 포함)."""
    if not gsheet.available():
        log("GSHEET_SA_JSON 미설정 — 시트 모드를 건너뜁니다 (서비스 계정 키 필요)")
        return
    sheet_title = gsheet.resolve_title()
    header = (gsheet.read(f"A1:{LAST_COL}1", sheet_title) or [[]])[0]
    cols = resolve_columns(header)
    rows = gsheet.read(f"A2:{LAST_COL}1000", sheet_title)

    pending = find_pending(rows, cols)
    backfill = find_structure_backfill(rows, cols, skip=set(pending))

    # 색칠(=수정·확인 완료) 신호 읽기 — 이미지 디벨롭(Q)·만든 제목(S) 배경색
    q_idx, s_idx = cols["image_develop"], cols["made_title"]
    lo, hi = min(q_idx, s_idx), max(q_idx, s_idx)
    try:
        raw_bgs = gsheet.read_backgrounds(
            f"{col_letter(lo)}2:{col_letter(hi)}{len(rows) + 1}", sheet_title)
    except Exception as e:
        log(f"배경색 읽기 실패(렌더 단계 건너뜀): {e}")
        raw_bgs = []
    bg_pairs = [[(r[q_idx - lo] if q_idx - lo < len(r) else None),
                 (r[s_idx - lo] if s_idx - lo < len(r) else None)] for r in raw_bgs]
    render_ready = find_render_ready(rows, cols, bg_pairs)

    if not pending and not backfill and not render_ready:
        log("처리할 행 없음 (L+M 대기 없음, J 백필 없음, 색칠 완료 렌더 대상 없음)")
        return

    # ① J(영상 문구 분석) 백필 — 구조분석만 가볍게. 빈 E~H·I·K도 이때 함께 채운다.
    for i in backfill[:backfill_max]:
        row, rownum = rows[i], i + 2
        bench = {"url": _cell(row, cols["url"]), "title": _cell(row, cols["title"])}
        ocr = ocr_benchmark(bench["url"]) if bench["url"] else {}
        bench["copy"] = ocr.get("copy", "") or _cell(row, cols["copy_emotion"])
        bench["image"] = ocr.get("image", "") or _cell(row, cols["image_emotion"])
        topic = _cell(row, cols["my_keyword"]) or _cell(row, cols["date_kw"]) or "(키워드 미정)"
        log(f"행{rownum} J 백필: {bench['title'][:30] or bench['url']}")
        try:
            analysis = analyze(topic, audience, bench)
        except Exception as e:
            log(f"  행{rownum} 백필 실패: {e}")
            continue
        v, e = analysis.get("viewer", {}), analysis.get("emotion", {})
        upd = {}
        for key, value in (
            ("structure", structure_cell(analysis)),
            ("situation", v.get("situation", "")), ("worry", v.get("worry", "")),
            ("desire", v.get("desire", "")), ("plan", v.get("plan", "")),
            ("copy_emotion", emotion_cell(e.get("copy_category", ""), e.get("copy_score", ""),
                                          f"{bench.get('copy', '')} — {e.get('reason', '')}")),
            ("image_emotion", emotion_cell(e.get("image_category", ""),
                                           e.get("image_score", ""), bench.get("image", ""))),
        ):
            if value and not _cell(row, cols[key]):
                upd[col_letter(cols[key])] = value
        # 핫비디오 재료가 있으면 P(핫비디오로 문구 디벨롭)도 채운다
        if not _cell(row, cols["hot_develop"]):
            hot = hot_video_develop(topic, row, cols, analysis)
            if hot:
                upd[col_letter(cols["hot_develop"])] = hot_develop_cell(hot)
        for letter, value in upd.items():
            gsheet.update(f"{letter}{rownum}", [[value]], sheet_title)
        log(f"  행{rownum} J 백필 완료 ({', '.join(sorted(upd))})")

    # ② 색칠 완료 행 렌더 — Q·S 둘 다 색칠 + R 비면 확정 사양으로 썸네일 생성
    for i in render_ready:
        row, rownum = rows[i], i + 2
        topic = _cell(row, cols["my_keyword"]) or _cell(row, cols["date_kw"]) or "썸네일"
        copy, title = parse_made_title(_cell(row, cols["made_title"]))
        log(f"행{rownum} 렌더 (색칠 확인): {copy[:30]}")
        import os
        from urllib.parse import quote
        # 확정 렌더는 Q열 지시대로 AI 생성 우선 (사용자가 DG_PHOTO_ORDER를 정했으면 존중)
        prev_order = os.environ.get("DG_PHOTO_ORDER")
        if not prev_order:
            os.environ["DG_PHOTO_ORDER"] = "generate,stock,owned"
        try:
            spec = render_spec(topic, copy, title, _cell(row, cols["image_develop"]))
            # 킥커(좌상단 문구)는 브랜딩 고정 — "현직 초등 교사가 알려주는"
            spec["label"] = os.getenv("DG_THUMB_KICKER", "").strip() or KICKER_DEFAULT
            # 실제 피부·스냅샷 질감 프롬프트를 항상 덧붙인다 (사용자 지정 리얼리즘)
            if spec.get("photo_prompt"):
                spec["photo_prompt"] = f"{spec['photo_prompt']}, {REALISM}"
            # 참조 이미지(실제 책 표지 등)가 있으면 그걸 반영해 장면 생성
            assets = find_assets(topic)
            if assets:
                from orchestrator import image_gen
                edit_prompt = (
                    f"{spec.get('photo_prompt') or spec.get('image_desc', '')}. "
                    "The child is holding and reading the exact book shown in the "
                    "reference image — reproduce the book cover design faithfully "
                    f"(do not redesign it). {REALISM}")
                bg_file = image_gen.edit_with_refs(edit_prompt, assets,
                                                   str(out / ".imgcache"))
                if bg_file:
                    spec["_bg_file"] = bg_file
                    log(f"  참조 이미지 {len(assets)}장 반영 (data/thumbnail_assets)")
                else:
                    log("  참조 이미지 편집 실패 — 일반 생성으로 진행")
            # v1(도현체 확정 스타일) + v2(검은고딕 중앙, 가독성 비교) 두 버전 렌더
            spec_v2 = dict(spec, style="v2")
            paths = render([spec, spec_v2], out, local_imgs,
                           prefix=f"final_{_file_token(topic)[:16] or 'x'}")
            rels = [save_render_to_vault(topic if i == 0 else f"{topic} v{i + 1}",
                                         p, p.with_suffix(".jpg"))
                    for i, p in enumerate(paths)]
        except Exception as e:
            log(f"  행{rownum} 렌더 실패: {e}")
            continue
        finally:
            if not prev_order:
                os.environ.pop("DG_PHOTO_ORDER", None)
        from vault_pipeline import telegram_notify
        # 저장소가 공개라 raw URL이 열린다 → R열 셀 안에 이미지 자체를 표시 (v1 기준)
        repo = os.getenv("GITHUB_REPOSITORY", "dream0grow/dream-grow-content-automation")
        branch = os.getenv("GITHUB_REF_NAME", "main")
        raw_url = (f"https://raw.githubusercontent.com/{repo}/{quote(branch)}/vault/"
                   f"{quote(rels[0])}")
        gsheet.update(f"{col_letter(cols['made_thumb'])}{rownum}",
                      [[f'=IMAGE("{raw_url}")']], sheet_title)
        # 작업 완료 표시: 사람이 칠한 노랑 → 파랑 (노랑=컨펌 완료, 파랑=렌더 완료)
        try:
            gsheet.color_cells(rownum, [cols["image_develop"], cols["made_title"]], DONE_BLUE)
        except Exception as e:
            log(f"  행{rownum} 완료색(파랑) 표시 실패(렌더는 정상): {e}")
        labels = ("v1 도현체", "v2 검은고딕")
        sent = 0
        for p, rel, lab in zip(paths, rels, labels):
            sent += telegram_notify.send_photo(
                str(p.with_suffix(".jpg")),
                caption=f"🖼 썸네일 {lab}: {topic}\n{copy}\n{telegram_notify.note_url(rel)}")
        log(f"  행{rownum} 렌더 완료 → R열 =IMAGE(v1) + Q·S 파랑 + 텔레그램 {sent}장")

    # ③ 전체 처리 — 아래 행부터(확장 행 삽입이 위쪽 행 번호를 건드리지 않게)
    if pending:
        log(f"대기 행 {len(pending)}개 → 최대 {max_rows}개 처리 (아래부터)")
    for i in sorted(pending, reverse=True)[:max_rows]:
        row, rownum = rows[i], i + 2
        topic = _cell(row, cols["my_keyword"])
        bench = {"url": _cell(row, cols["url"]), "title": _cell(row, cols["title"])}
        ocr = ocr_benchmark(bench["url"]) if bench["url"] else {}
        bench["copy"] = ocr.get("copy", "")
        bench["image"] = ocr.get("image", "")
        if not bench["copy"]:
            log(f"  행{rownum}: 썸네일 OCR 불가 — 제목·기존 분석 텍스트로 진행")
            bench["image"] = bench.get("image") or _cell(row, cols["image_emotion"])
        log(f"행{rownum} 처리: 키워드={topic}")
        result = run_one(topic, audience, bench, expand_count, out, local_imgs,
                         save_vault=save_vault)
        hot = None
        if not _cell(row, cols["hot_develop"]):
            hot = hot_video_develop(topic, row, cols, result["analysis"])
        for letter, value in _row_updates(row, cols, result, bench, hot).items():
            gsheet.update(f"{letter}{rownum}", [[value]], sheet_title)
        log(f"  행{rownum} 시트 기록 완료")
        expand = result.get("expand")
        if expand and expand.get("expansions"):
            values = expansion_values(expand, row, cols)
            if values:
                insert_expansions(rownum, values, sheet_title)
                log(f"  확장 키워드 {len(values)}행을 행{rownum} 아래에 삽입·그룹")


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
    ensure_dohyeon()
    ensure_blackhansans()
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
