"""드림그로우 유튜브 채널아트 생성기.

프로필 사진의 칠판 초록을 메인 색으로, 핵심 메시지 한 문장을 얹은
2560x1440 배너 PNG를 렌더링한다. 텍스트·로고는 모든 기기에서 보이는
안전영역(중앙 1546x423) 안에만 배치한다.

실행:
    python3 -m branding.youtube_channel_art            # 전체 변형 렌더
    python3 -m branding.youtube_channel_art --safe     # 안전영역 가이드 오버레이 포함
출력: branding/out/channel_art_{a,b,c}.png
"""
from __future__ import annotations

import argparse
import glob
import html as _html
import os
import subprocess
import urllib.request
from pathlib import Path

W, H = 2560, 1440          # 유튜브 권장 해상도
SAFE_W, SAFE_H = 1546, 423  # 모든 기기 공통 노출 영역(중앙)

FONT_WEIGHTS = ("Black", "ExtraBold", "Bold", "SemiBold", "Regular")
FONT_BASE = ("https://raw.githubusercontent.com/orioncactus/pretendard/main/"
             "packages/pretendard/dist/public/static")

# 칠판 초록 팔레트 (프로필 사진 배경에서 추출)
BG_BASE = "#1E4B30"
BG_LIGHT = "#2B6642"
BG_DARK = "#122B1C"
CHALK_YELLOW = "#F7D97C"

VARIANTS = [
    {
        "key": "a",
        "chip": "성장하는 부모 커뮤니티",
        "headline": [("성장하는 부모가 ", None), ("최고의 선생님", CHALK_YELLOW), ("입니다", None)],
        "sub": "성장하는 부모, 행복한 가정 — 드림그로우",
    },
    {
        "key": "b",
        "chip": "성장하는 부모 커뮤니티 · 드림그로우",
        "headline": [("성장하는 부모, ", None), ("행복한 가정", CHALK_YELLOW)],
        "sub": "부모가 최고의 선생님입니다",
    },
    {
        "key": "c",
        "chip": "성장하는 부모 커뮤니티",
        "headline": [("부모가 자라면 ", None), ("아이의 세상", CHALK_YELLOW), ("도 자랍니다", None)],
        "hsize": 92,
        "sub": "성장하는 부모, 행복한 가정 — 드림그로우",
    },
]


def log(msg: str):
    print(f"[channel-art] {msg}", flush=True)


def chrome_path() -> str:
    override = os.getenv("DG_CHROME_PATH", "").strip()
    if override and Path(override).exists():
        return override
    root = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    for pat in (f"{root}/chromium-*/chrome-linux/chrome", f"{root}/chromium/chrome-linux/chrome"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return ""


def ensure_fonts():
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


# 칠판 질감: SVG 노이즈를 저투명 오버레이로 깐다
NOISE_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'>"
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/>"
    "<feColorMatrix type='saturate' values='0'/></filter>"
    "<rect width='300' height='300' filter='url(%23n)' opacity='0.55'/></svg>"
)

# 안전영역 밖 좌우에 옅게 두는 분필 낙서 (새싹 / 하트집)
SPROUT_SVG = """
<svg viewBox="0 0 200 200" fill="none" stroke="#FFFFFF" stroke-width="5"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M100 170 C100 130 100 110 100 90"/>
  <path d="M100 96 C70 92 52 74 50 44 C80 46 98 62 100 92 Z"/>
  <path d="M100 106 C130 102 148 84 150 54 C120 56 102 72 100 102 Z"/>
  <path d="M70 170 C80 178 120 178 130 170"/>
</svg>"""

HOME_SVG = """
<svg viewBox="0 0 200 200" fill="none" stroke="#FFFFFF" stroke-width="5"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M45 100 L100 52 L155 100"/>
  <path d="M60 92 L60 160 L140 160 L140 92"/>
  <path d="M100 140 C88 128 78 118 84 106 C90 96 100 100 100 108 C100 100 110 96 116 106 C122 118 112 128 100 140 Z"/>
</svg>"""


def _headline_html(parts) -> str:
    spans = []
    for text, color in parts:
        style = f" style='color:{color}'" if color else ""
        spans.append(f"<span{style}>{_html.escape(text)}</span>")
    return "".join(spans)


def art_html(v: dict, show_safe: bool = False) -> str:
    safe_guide = (
        f"<div style='position:absolute; left:{(W-SAFE_W)//2}px; top:{(H-SAFE_H)//2}px;"
        f" width:{SAFE_W}px; height:{SAFE_H}px; border:2px dashed rgba(255,80,80,.8);'></div>"
        if show_safe else ""
    )
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{W}px; height:{H}px; overflow:hidden;
       font-family:'Pretendard','Noto Sans KR',sans-serif; }}
.stage {{ position:relative; width:{W}px; height:{H}px;
  background:
    radial-gradient(ellipse 1700px 900px at 50% 46%, {BG_LIGHT} 0%, {BG_BASE} 55%, {BG_DARK} 100%);
}}
.noise {{ position:absolute; inset:0; background:url("{NOISE_SVG}"); opacity:.07; }}
.doodle {{ position:absolute; width:230px; height:230px; opacity:.14; }}
.doodle svg {{ width:100%; height:100%; }}
.safe {{ position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
  width:{SAFE_W}px; height:{SAFE_H}px; display:flex; flex-direction:column;
  align-items:center; justify-content:center; text-align:center; }}
.chip {{ display:inline-block; padding:14px 38px; border:2.5px solid rgba(255,255,255,.5);
  border-radius:999px; color:#EAF4EC; font-weight:600; font-size:33px;
  letter-spacing:8px; text-indent:8px; margin-bottom:38px; }}
.headline {{ color:#fff; font-weight:800; font-size:{v.get('hsize', 104)}px; line-height:1.22;
  letter-spacing:-2px; text-shadow:0 4px 24px rgba(0,0,0,.25); white-space:nowrap; }}
.sub {{ margin-top:30px; color:#DCEBDF; font-weight:500; font-size:42px;
  letter-spacing:2px; }}
.brand {{ margin-top:34px; color:rgba(255,255,255,.62); font-weight:700;
  font-size:27px; letter-spacing:14px; text-indent:14px; }}
</style></head><body><div class='stage'>
  <div class='noise'></div>
  <div class='doodle' style='left:170px; top:300px; transform:rotate(-8deg);'>{SPROUT_SVG}</div>
  <div class='doodle' style='right:170px; bottom:300px; transform:rotate(6deg);'>{HOME_SVG}</div>
  <div class='safe'>
    <div class='chip'>{_html.escape(v['chip'])}</div>
    <div class='headline'>{_headline_html(v['headline'])}</div>
    <div class='sub'>{_html.escape(v['sub'])}</div>
    <div class='brand'>DREAM GROW</div>
  </div>
  {safe_guide}
</div></body></html>"""


def render(show_safe: bool = False) -> list[Path]:
    from playwright.sync_api import sync_playwright
    ensure_fonts()
    out = Path(__file__).parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with sync_playwright() as p:
        launch_kw = {"args": ["--no-sandbox"]}
        cpath = chrome_path()
        if cpath:
            launch_kw["executable_path"] = cpath
        browser = p.chromium.launch(**launch_kw)
        page = browser.new_page(viewport={"width": W, "height": H})
        for v in VARIANTS:
            page.set_content(art_html(v, show_safe=show_safe))
            page.wait_for_timeout(120)
            suffix = "_safe" if show_safe else ""
            fp = out / f"channel_art_{v['key']}{suffix}.png"
            page.screenshot(path=str(fp))
            paths.append(fp)
            log(f"변형 {v['key']} → {fp}")
        browser.close()
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--safe", action="store_true", help="안전영역 가이드 표시")
    render(show_safe=ap.parse_args().safe)
