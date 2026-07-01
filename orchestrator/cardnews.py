"""카드뉴스 자동 완성 - 초안을 '실사진 + 오버레이' 편집형 카드 슬라이드(PNG)로 렌더링.

레퍼런스(bark_mag·K-TITANS)처럼 실제 사진을 풀블리드로 깔고, 하단 그라데이션 위에
Pretendard 볼드 카피를 얹는다. 카테고리 칩·STEP 라벨·페이지 번호 포함.

사진 소스 우선순위:
  1) --photos-dir 로컬 이미지(브랜드 소유 사진 라이브러리 / 데모)
  2) PEXELS_API_KEY 있으면 슬라이드별 photo_query로 스톡 검색 (운영 GitHub Actions에서 동작)
  3) 없으면 어두운 그라데이션 폴백

폰트: 시스템에 Pretendard가 설치돼 있으면 사용, 없으면 ensure_fonts()가 GitHub에서 받아 설치.

실행:
  python3 -m orchestrator.cardnews --from-preview <preview_out> --photos-dir <이미지폴더> --out <출력>
  python3 -m orchestrator.cardnews --topic "주제" --out <출력>   # PEXELS_API_KEY로 사진 자동
"""
import argparse
import base64
import glob
import html as _html
import json
import mimetypes
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import agent_dialogue, image_gen, llm, photo_judge, prompts, stock

CARD = 1080
HANDLE = os.getenv("DG_CARDNEWS_HANDLE", "@dream_grow")
FONT_WEIGHTS = ("Black", "ExtraBold", "Bold", "SemiBold", "Regular")
FONT_BASE = ("https://raw.githubusercontent.com/orioncactus/pretendard/main/"
             "packages/pretendard/dist/public/static")


def log(msg: str):
    print(f"[cardnews] {msg}", flush=True)


def chrome_path() -> str:
    """사전 설치된 Chromium 경로를 찾는다. 못 찾으면 ''를 반환해 Playwright 자동 탐지에 맡긴다."""
    override = os.getenv("DG_CHROME_PATH", "").strip()
    if override and Path(override).exists():
        return override
    root = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    for pat in (f"{root}/chromium-*/chrome-linux/chrome", f"{root}/chromium/chrome-linux/chrome"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return ""  # Actions 등: playwright install한 기본 위치를 자동 사용


def ensure_fonts():
    """Pretendard가 시스템에 없으면 GitHub에서 받아 설치한다 (Actions/로컬 공통)."""
    try:
        out = subprocess.run(["fc-list"], capture_output=True, text=True, timeout=20).stdout
        if "Pretendard" in out:
            return
    except Exception:
        pass
    dest = Path("/usr/share/fonts/pretendard")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for w in FONT_WEIGHTS:
            fp = dest / f"Pretendard-{w}.otf"
            if not fp.exists():
                urllib.request.urlretrieve(f"{FONT_BASE}/Pretendard-{w}.otf", fp)
        subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=60)
        log("Pretendard 폰트 설치 완료")
    except Exception as e:
        log(f"Pretendard 설치 실패(시스템 기본 폰트로 진행): {e}")


# ---------- 슬라이드 텍스트 ----------

def make_slides(topic: str, core: str, draft: str, body_count: int = 5) -> dict:
    """카드뉴스 계획을 생성한다.

    반환: {"cover_media": "video|photo", "cover_reason": str,
           "video_motion": str, "slides": [...]}
    """
    from orchestrator import cardnews_benchmark
    benchmark = cardnews_benchmark.load() or "(최근 벤치마킹 자료 없음 — 기본 원칙으로 작성)"
    data = llm.call_json(
        prompts.CARDNEWS.format(
            topic=topic, core=core, draft=draft[:6000],
            body_count=body_count, benchmark=benchmark[:4000]),
        system=prompts.get_system(),
    )
    return data


# ---------- 사진 소스 ----------

def _file_to_bg(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f"url('data:{mime};base64,{b64}')"


def resolve_photo(slide: dict, local_imgs: list[str], idx: int, cache_dir: str) -> str:
    """배경 사진의 CSS background-image 값을 만든다.

    우선순위: 1) 브랜드 소유 사진  2) 실물 스톡(Pexels/Unsplash)  3) AI 생성(한국인 중심)
             4) 그라데이션 폴백. (DG_PHOTO_ORDER 로 순서 조정 가능)
    """
    order = os.getenv("DG_PHOTO_ORDER", "owned,stock,generate").split(",")
    for src in (s.strip() for s in order):
        if src == "owned" and local_imgs:
            return _file_to_bg(local_imgs[idx % len(local_imgs)])
        if src == "stock":
            hit = stock.fetch((slide.get("photo_query") or "").strip(), cache_dir)
            if hit:
                return _file_to_bg(hit)
        if src == "generate":
            gp = (slide.get("photo_prompt") or "").strip()
            gen = image_gen.generate(gp, cache_dir) if gp else None
            if gen:
                return _file_to_bg(gen)
    return ""  # 폴백: 그라데이션


def resolve_cover_photo(slide: dict, local_imgs: list[str], cache_dir: str) -> str:
    """표지 배경: 소유 사진 → 실물 스톡(후킹·공감·어울림 심사) → 통과 못 하면 AI 생성.

    표지는 후킹이 생명이라, 스톡이 '딱 맞고 후킹되는' 사진일 때만 쓰고
    애매하면(또는 심사 불가하면) 새로 생성한다.
    """
    if local_imgs:
        return _file_to_bg(local_imgs[0])
    ctx = f"{slide.get('title','')} / {slide.get('body','')}"
    cand = stock.fetch((slide.get("photo_query") or "").strip(), cache_dir)
    if cand:
        verdict = photo_judge.judge(cand, ctx)
        if verdict is not None and verdict.get("ok"):
            log(f"표지 사진=스톡 채택 (심사 {verdict['score']}: {verdict.get('reason','')})")
            return _file_to_bg(cand)
        log(f"표지 사진=스톡 부적합/심사불가 → 생성 "
            f"({verdict['score'] if verdict else 'n/a'})")
    gp = (slide.get("photo_prompt") or "").strip()
    gen = image_gen.generate(gp, cache_dir) if gp else None
    if gen:
        return _file_to_bg(gen)
    if cand:  # 생성까지 실패하면 스톡이라도
        return _file_to_bg(cand)
    return ""


# ---------- 렌더 ----------

def _css() -> str:
    return """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1080px; height:1080px; }
.card { width:1080px; height:1080px; position:relative; overflow:hidden;
  font-family:'Pretendard','Noto Sans KR',sans-serif; color:#fff; background:#14110f; }
.photo { position:absolute; inset:0; background-size:cover; background-position:center; }
.nophoto { position:absolute; inset:0;
  background:radial-gradient(120% 90% at 70% 15%, #4a4038 0%, #211c18 55%, #100d0b 100%); }
.scrim { position:absolute; inset:0; background:linear-gradient(to top,
  rgba(0,0,0,.94) 0%, rgba(0,0,0,.82) 22%, rgba(0,0,0,.28) 52%, rgba(0,0,0,.12) 72%,
  rgba(0,0,0,.42) 100%); }
.top { position:absolute; top:54px; left:66px; right:66px; display:flex;
  justify-content:space-between; align-items:center; font-weight:700; font-size:28px;
  letter-spacing:2px; opacity:.92; }
.wrap { position:absolute; left:66px; right:66px; bottom:96px; }
.chip { display:inline-block; background:#ffd21e; color:#14110f; font-weight:800;
  font-size:26px; letter-spacing:-.5px; padding:9px 20px; border-radius:7px; }
.step { margin-top:30px; font-size:26px; font-weight:700; letter-spacing:5px; opacity:.9; }
.rule { width:62px; height:4px; background:#fff; opacity:.85; border-radius:3px; margin:16px 0 20px; }
.title { font-family:'Pretendard'; font-weight:800; letter-spacing:-2px;
  line-height:1.26; text-shadow:0 3px 26px rgba(0,0,0,.55); }
.body { margin-top:26px; font-weight:500; line-height:1.6; letter-spacing:-.5px;
  opacity:.94; text-shadow:0 2px 18px rgba(0,0,0,.6); }
.cover .title { font-size:88px; font-weight:800; }
.cover .body  { font-size:40px; font-weight:600; }
.content .title { font-size:74px; }
.content .body  { font-size:36px; }
.closing .title { font-size:70px; }
.closing .body  { font-size:38px; font-weight:600; }
.slogan { position:absolute; left:66px; right:66px; bottom:56px; font-size:28px;
  font-weight:800; letter-spacing:-.5px; opacity:.95; }
"""


def slide_html(slide: dict, i: int, total: int, bg: str, step_no: int) -> str:
    kind = slide.get("kind", "content")
    label = _html.escape((slide.get("label") or "드림그로우").strip())
    title = _html.escape((slide.get("title") or "").strip()).replace("\n", "<br>")
    body = _html.escape((slide.get("body") or "").strip()).replace("\n", "<br>")
    photo_div = f'<div class="photo" style="background-image:{bg}"></div>' if bg else '<div class="nophoto"></div>'

    if kind == "cover":
        block = f'<span class="chip">{label}</span><div class="title">{title}</div><div class="body">{body}</div>'
        extra = ""
    elif kind == "closing":
        block = f'<span class="chip">{label}</span><div class="title">{title}</div><div class="body">{body}</div>'
        extra = '<div class="slogan">아이와 부모의 꿈을 키웁니다 · Dream_Grow</div>'
    else:
        block = (f'<span class="chip">{label}</span>'
                 f'<div class="step">STEP {step_no:02d}</div><div class="rule"></div>'
                 f'<div class="title">{title}</div><div class="body">{body}</div>')
        extra = ""

    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_css()}</style></head>"
            f"<body><div class='card {kind}'>{photo_div}<div class='scrim'></div>"
            f"<div class='top'><span>{_html.escape(HANDLE)}</span><span>{i} / {total}</span></div>"
            f"<div class='wrap'>{block}</div>{extra}</div></body></html>")


def render(slides: list[dict], local_imgs: list[str], out: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    total = len(slides)
    paths: list[Path] = []
    with sync_playwright() as p:
        cpath = chrome_path()
        launch_kw = {"args": ["--no-sandbox"]}
        if cpath:
            launch_kw["executable_path"] = cpath
        browser = p.chromium.launch(**launch_kw)
        page = browser.new_page(viewport={"width": CARD, "height": CARD}, device_scale_factor=2)
        cache_dir = str(out / ".imgcache")
        step = 0
        for i, s in enumerate(slides, 1):
            if s.get("kind") == "content":
                step += 1
            if s.get("kind") == "cover":
                bg = resolve_cover_photo(s, local_imgs, cache_dir)
            else:
                bg = resolve_photo(s, local_imgs, i - 1, cache_dir)
            page.set_content(slide_html(s, i, total, bg, step))
            page.wait_for_timeout(150)  # 원격 이미지 로드 여유
            fp = out / f"card_{i:02d}_{s.get('kind','content')}.png"
            page.screenshot(path=str(fp))
            paths.append(fp)
            log(f"슬라이드 {i}/{total} ({s.get('kind')}): {s.get('title','')[:22]} → {fp.name}")
        browser.close()
    return paths


def contact_sheet(paths: list[Path], out: Path) -> Path:
    imgs = "".join(f'<figure><img src="{p.name}"><figcaption>{p.stem}</figcaption></figure>' for p in paths)
    page = ("<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'><title>카드뉴스 미리보기</title>"
            "<style>body{background:#1b1917;margin:0;padding:28px;font-family:sans-serif}"
            "h1{color:#fff;font-size:20px;margin:0 0 20px}.grid{display:flex;flex-wrap:wrap;gap:18px}"
            "figure{margin:0;background:#000;border-radius:14px;overflow:hidden;width:330px}"
            "img{width:330px;height:330px;display:block}"
            "figcaption{color:#bba;font-size:12px;padding:7px 10px}</style></head>"
            f"<body><h1>🖼️ 카드뉴스 미리보기 — 총 {len(paths)}장</h1><div class='grid'>{imgs}</div></body></html>")
    fp = out / "cardnews_preview.html"
    fp.write_text(page, encoding="utf-8")
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-preview", default="")
    ap.add_argument("--topic", default="")
    ap.add_argument("--audience", default="초등 저학년 학부모")
    ap.add_argument("--photos-dir", default="")
    ap.add_argument("--body-count", type=int, default=5)
    ap.add_argument("--out", default="cardnews_out")
    args = ap.parse_args()
    out = Path(args.out)
    ensure_fonts()

    if args.from_preview:
        src = Path(args.from_preview)
        brief = json.loads((src / "00_brief.json").read_text(encoding="utf-8"))
        df = src / "thread_draft.md"
        draft = df.read_text(encoding="utf-8") if df.exists() else ""
        topic, core = brief.get("brief_title", ""), brief.get("core_message", "")
    else:
        topic = args.topic.strip() or "초등 아이 훈육 고민"
        brief = llm.call_json(
            prompts.BRIEF.format(keyword=topic, topic=topic, audience=args.audience, context=""),
            system=prompts.get_system())
        core = brief.get("core_message", "")
        log(f"초안 생성 중: {topic}")
        draft = agent_dialogue.run_draft_dialogue(brief, "thread")["draft"]

    local_imgs = []
    if args.photos_dir:
        local_imgs = sorted(
            g for ext in ("jpg", "jpeg", "png", "webp")
            for g in glob.glob(str(Path(args.photos_dir) / f"*.{ext}")))
        log(f"로컬 사진 {len(local_imgs)}장 사용")

    log(f"카드뉴스 슬라이드 구성: {topic}")
    plan = make_slides(topic, core, draft, args.body_count)
    slides = plan.get("slides", [])
    if not slides:
        log("슬라이드 생성 실패")
        return
    cover_media = (plan.get("cover_media") or "photo").strip().lower()
    log(f"표지 미디어 판단: {cover_media.upper()} — {plan.get('cover_reason', '')}")
    if cover_media == "video":
        log(f"  (영상 움직임: {plan.get('video_motion', '')[:120]})")
        log("  ※ 영상은 힉스필드 세션에서 온디맨드 생성. 여기선 정지 표지 이미지로 렌더.")
    out.mkdir(parents=True, exist_ok=True)
    paths = render(slides, local_imgs, out)
    (out / "cardnews_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    sheet = contact_sheet(paths, out)
    log(f"완료: {len(paths)}장 → {out.resolve()} ({sheet.name})")


if __name__ == "__main__":
    main()
