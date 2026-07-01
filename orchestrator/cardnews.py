"""카드뉴스 자동 완성 - 초안을 브랜드 카드 슬라이드(PNG)로 렌더링한다.

브리프/초안을 CARDNEWS 프롬프트로 슬라이드(표지·본문·마무리)로 재구성한 뒤,
Playwright(사전 설치된 Chromium)로 각 슬라이드를 1080x1080 PNG로 렌더링한다.
외부 유료 API 없이 컨테이너 안에서 완결된다.

실행:
  python3 -m orchestrator.cardnews --from-preview <preview_out 디렉터리> --out <출력>
  python3 -m orchestrator.cardnews --topic "주제" --audience "초등 저학년 학부모" --out <출력>
"""
import argparse
import glob
import html as _html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import agent_dialogue, llm, prompts

CARD_W = CARD_H = 1080


def log(msg: str):
    print(f"[cardnews] {msg}", flush=True)


def chrome_path() -> str:
    """사전 설치된 Chromium 실행 파일을 찾는다."""
    override = os.getenv("DG_CHROME_PATH", "").strip()
    if override and Path(override).exists():
        return override
    root = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    for pat in (f"{root}/chromium-*/chrome-linux/chrome",
                f"{root}/chromium/chrome-linux/chrome"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    raise RuntimeError(f"Chromium 실행 파일을 찾지 못함 (PLAYWRIGHT_BROWSERS_PATH={root})")


# ---------- 슬라이드 텍스트 생성 ----------

def make_slides(topic: str, core: str, draft: str, body_count: int = 5) -> list[dict]:
    data = llm.call_json(
        prompts.CARDNEWS.format(
            topic=topic, core=core, draft=draft[:6000], body_count=body_count,
        ),
        system=prompts.get_system(),
    )
    return data.get("slides", [])


# ---------- HTML/CSS 렌더 ----------

BASE_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1080px; height:1080px; }
.card {
  width:1080px; height:1080px; position:relative; overflow:hidden;
  font-family:'Noto Sans KR','Apple SD Gothic Neo','Malgun Gothic',sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  padding:96px 92px;
}
.wordmark { position:absolute; top:64px; left:92px; font-size:30px; font-weight:800;
  letter-spacing:1px; opacity:.9; }
.pagenum { position:absolute; top:60px; right:92px; font-size:30px; font-weight:700;
  width:64px; height:64px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; }
.title { font-weight:800; line-height:1.32; letter-spacing:-1px; }
.body { line-height:1.62; letter-spacing:-.5px; font-weight:500; }
.foot { position:absolute; bottom:60px; left:92px; right:92px; font-size:26px;
  font-weight:600; opacity:.75; }

/* 표지 */
.cover { background:linear-gradient(155deg,#ffb877 0%,#ff7e5f 62%,#f0574a 100%); color:#fff; }
.cover .title { font-size:82px; }
.cover .body { font-size:40px; margin-top:36px; font-weight:600; opacity:.95; }
.cover .wordmark { color:#fff; }

/* 본문 */
.content { background:#fff8ef; color:#2c1c0f; }
.content .accent { width:96px; height:12px; border-radius:8px; background:#ff7e5f; margin-bottom:40px; }
.content .title { font-size:60px; color:#b8431f; }
.content .body { font-size:44px; margin-top:34px; color:#4a3320; }
.content .pagenum { background:#ff7e5f; color:#fff; }
.content .wordmark { color:#c9814e; }

/* 마무리 */
.closing { background:linear-gradient(155deg,#3aa981 0%,#2f8f6f 100%); color:#fff; }
.closing .label { font-size:34px; font-weight:700; opacity:.9; margin-bottom:24px; }
.closing .title { font-size:66px; }
.closing .body { font-size:40px; margin-top:32px; font-weight:600; opacity:.96; }
.closing .slogan { position:absolute; bottom:80px; left:92px; right:92px;
  font-size:34px; font-weight:800; }
.closing .wordmark { color:#fff; }
"""


def _fmt_body(text: str) -> str:
    return _html.escape((text or "").strip()).replace("\n", "<br>")


def slide_html(slide: dict, idx: int, total_body: int, body_no: int) -> str:
    kind = slide.get("kind", "content")
    title = _html.escape((slide.get("title") or "").strip())
    body = _fmt_body(slide.get("body"))
    if kind == "cover":
        inner = (f'<div class="wordmark">드림그로우</div>'
                 f'<div class="title">{title}</div>'
                 f'<div class="body">{body}</div>')
        cls = "cover"
    elif kind == "closing":
        inner = (f'<div class="wordmark">드림그로우</div>'
                 f'<div class="label">오늘 딱 하나</div>'
                 f'<div class="title">{title}</div>'
                 f'<div class="body">{body}</div>'
                 f'<div class="slogan">아이와 부모의 꿈을 키웁니다 · Dream_Grow</div>')
        cls = "closing"
    else:
        inner = (f'<div class="wordmark">드림그로우</div>'
                 f'<div class="pagenum">{body_no}</div>'
                 f'<div class="accent"></div>'
                 f'<div class="title">{title}</div>'
                 f'<div class="body">{body}</div>')
        cls = "content"
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{BASE_CSS}</style>"
            f"</head><body><div class='card {cls}'>{inner}</div></body></html>")


def render(slides: list[dict], out: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    total_body = sum(1 for s in slides if s.get("kind") == "content")
    paths: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": CARD_W, "height": CARD_H},
                                device_scale_factor=2)
        body_no = 0
        for i, s in enumerate(slides, 1):
            if s.get("kind") == "content":
                body_no += 1
            page.set_content(slide_html(s, i, total_body, body_no))
            fp = out / f"card_{i:02d}_{s.get('kind','content')}.png"
            page.screenshot(path=str(fp))
            paths.append(fp)
            log(f"슬라이드 {i} ({s.get('kind')}): {s.get('title','')[:24]} → {fp.name}")
        browser.close()
    return paths


def contact_sheet(paths: list[Path], out: Path) -> Path:
    imgs = "".join(
        f'<figure><img src="{p.name}"><figcaption>{p.stem}</figcaption></figure>'
        for p in paths
    )
    htmlpage = (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        "<title>카드뉴스 미리보기</title><style>"
        "body{background:#33302e;margin:0;padding:28px;font-family:sans-serif}"
        "h1{color:#fff;font-size:20px;margin:0 0 20px}"
        ".grid{display:flex;flex-wrap:wrap;gap:20px}"
        "figure{margin:0;background:#000;border-radius:14px;overflow:hidden;width:320px}"
        "img{width:320px;height:320px;display:block}"
        "figcaption{color:#cbb;font-size:13px;padding:8px 10px}</style></head>"
        f"<body><h1>🖼️ 카드뉴스 자동완성 미리보기 — 총 {len(paths)}장</h1>"
        f"<div class='grid'>{imgs}</div></body></html>"
    )
    fp = out / "cardnews_preview.html"
    fp.write_text(htmlpage, encoding="utf-8")
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-preview", default="")
    ap.add_argument("--topic", default="")
    ap.add_argument("--audience", default="초등 저학년 학부모")
    ap.add_argument("--body-count", type=int, default=5)
    ap.add_argument("--out", default="cardnews_out")
    args = ap.parse_args()
    out = Path(args.out)

    if args.from_preview:
        src = Path(args.from_preview)
        brief = json.loads((src / "00_brief.json").read_text(encoding="utf-8"))
        draft_file = src / "thread_draft.md"
        draft = draft_file.read_text(encoding="utf-8") if draft_file.exists() else ""
        topic = brief.get("brief_title", "")
        core = brief.get("core_message", "")
    else:
        topic = args.topic.strip() or "초등 아이 훈육 고민"
        brief = llm.call_json(
            prompts.BRIEF.format(keyword=topic, topic=topic, audience=args.audience, context=""),
            system=prompts.get_system(),
        )
        core = brief.get("core_message", "")
        log(f"초안 생성 중: {topic}")
        draft = agent_dialogue.run_draft_dialogue(brief, "thread")["draft"]

    log(f"카드뉴스 슬라이드 구성: {topic}")
    slides = make_slides(topic, core, draft, args.body_count)
    if not slides:
        log("슬라이드 생성 실패")
        return
    (out / "slides.json").parent.mkdir(parents=True, exist_ok=True)
    paths = render(slides, out)
    (out / "slides.json").write_text(
        json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")
    sheet = contact_sheet(paths, out)
    log(f"완료: {len(paths)}장 → {out.resolve()} (미리보기: {sheet.name})")


if __name__ == "__main__":
    main()
