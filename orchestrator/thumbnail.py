"""유튜브 썸네일 자동화 — 주제 입력 → 문구(기대/증거/의문/공감) 구조 생성·분석·디벨롭 → PNG 렌더.

사용자의 벤치마킹 구글 시트 워크플로우를 그대로 코드로 옮겼다:
  ① 분석: 상황/고민/욕구/계획 (시청자 심리)
  ② 문구 생성: data/thumbnail_patterns.md의 구조 공식을 주제로 치환 — 카테고리별 후보 8개
  ③ 디벨롭: 비평 후 카테고리별 최강 1개씩 최종 완성 (두 줄 타이포 + 강조어 + 신뢰 칩)
  ④ 렌더: 1280×720 실사진 풀블리드 + Pretendard 오버레이 (cardnews와 같은 사진 소스 우선순위)

산출물:
  - out/thumb_XX_{카테고리}.png (+ .jpg — 유튜브 업로드용 2MB 이하 목표)
  - out/thumbnail_plan.json, out/썸네일_{주제}.md (시트에 붙여넣기 좋은 표 형식)
  - 볼트 `05 리뷰/대기/썸네일_{주제}.md` 저장(--no-vault로 끔) → 기존 script_feedback이
    텔레그램 알림·답장 핑퐁을 그대로 이어준다.

실행:
  python3 -m orchestrator.thumbnail --topic "초등 고전 독서"
  python3 -m orchestrator.thumbnail --topic "..." --benchmark-copy "벤치 썸네일 문구" \
      --benchmark-url "https://youtube.com/..." --photos-dir 사진폴더 --out thumbnail_out
"""
import argparse
import html as _html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import llm, prompts
from orchestrator.cardnews import chrome_path, ensure_fonts, resolve_photo

W, H = 1280, 720
CATEGORIES = ("기대", "증거", "의문", "공감")
PATTERNS_FILE = Path(__file__).resolve().parent.parent / "data" / "thumbnail_patterns.md"
# 원고 핑퐁과 같은 폴더 — script_feedback이 `검수상태: 대기` + 최근 생성일이면 알림을 보낸다
REVIEW_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"


def log(msg: str):
    print(f"[thumbnail] {msg}", flush=True)


def load_patterns() -> str:
    return PATTERNS_FILE.read_text(encoding="utf-8")


def _file_token(s: str) -> str:
    return re.sub(r"\s+", "", re.sub(r'[\\/:*?"<>|#^\[\]]', "", s or "")).strip()


# ---------- ①② 분석 + 문구 후보 생성 ----------

def generate_candidates(topic: str, audience: str,
                        benchmark_copy: str = "", benchmark_url: str = "") -> dict:
    """분석(상황/고민/욕구/계획) + 카테고리별 문구 후보를 한 번에 생성한다."""
    benchmark_block = ""
    if benchmark_copy or benchmark_url:
        benchmark_block = (
            "[이번에 벤치마킹할 실제 썸네일 — 이 문구의 구조를 최우선으로 분해·치환할 것]\n"
            f"문구: {benchmark_copy or '(없음 — URL만 기록)'}\n"
            f"영상: {benchmark_url or '(URL 없음)'}"
        )
    data = llm.call_json(
        prompts.THUMBNAIL.format(
            patterns=load_patterns()[:9000], benchmark_block=benchmark_block,
            topic=topic, audience=audience),
        system=prompts.get_system(), max_tokens=6000,
    )
    if not data.get("candidates"):
        raise RuntimeError("썸네일 문구 후보 생성 실패 (candidates 비어 있음)")
    return data


# ---------- ③ 디벨롭 (비평 → 최종) ----------

def develop(topic: str, audience: str, data: dict, count: int = 4) -> list[dict]:
    """후보를 비평하고 카테고리별 최강 문구를 최종 완성한다."""
    out = llm.call_json(
        prompts.THUMBNAIL_DEVELOP.format(
            topic=topic, audience=audience, count=count,
            analysis=json.dumps(data.get("analysis", {}), ensure_ascii=False, indent=1),
            candidates=json.dumps(data.get("candidates", []), ensure_ascii=False, indent=1)),
        system=prompts.get_system(), max_tokens=4000,
    )
    picks = out.get("picks", [])
    if not picks:
        raise RuntimeError("썸네일 디벨롭 실패 (picks 비어 있음)")
    return picks[:count]


# ---------- ④ 렌더 (1280×720) ----------

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


def render(picks: list[dict], out: Path, local_imgs: list[str] | None = None) -> list[Path]:
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
            cat = _file_token(pick.get("category") or "기타") or "기타"
            png = out / f"thumb_{i:02d}_{cat}.png"
            page.screenshot(path=str(png))
            page.screenshot(path=str(out / f"thumb_{i:02d}_{cat}.jpg"),
                            type="jpeg", quality=90)
            paths.append(png)
            log(f"썸네일 {i}/{len(picks)} [{cat}] {pick.get('copy','')[:24]} → {png.name}")
        browser.close()
    return paths


# ---------- 산출물 (시트 형식 md + 볼트 저장) ----------

def build_md(topic: str, audience: str, data: dict, picks: list[dict],
             benchmark_copy: str = "", benchmark_url: str = "") -> str:
    """분석·후보·최종 픽을 시트 구조 그대로 담은 마크다운을 만든다 (시트에 붙여넣기 용이)."""
    a = data.get("analysis", {})
    lines = [
        f"# 썸네일 기획 — {topic}", "",
        f"- 타겟: {audience}",
    ]
    if benchmark_copy or benchmark_url:
        lines.append(f"- 벤치마킹: {benchmark_copy} {benchmark_url}".rstrip())
    lines += [
        "", "## 분석 (상황 → 고민 → 욕구 → 계획)", "",
        "| 상황 | 고민 | 욕구 | 계획 |", "|---|---|---|---|",
        "| {} | {} | {} | {} |".format(*(str(a.get(k, "")).replace("|", "／").replace("\n", " ")
                                         for k in ("situation", "worry", "desire", "plan"))),
        "", "## 최종 픽 (디벨롭 완료)", "",
        "| 카테고리 | 썸네일 문구 | 구조분석 | 영상 제목 | 그림 | 디벨롭 메모 |",
        "|---|---|---|---|---|---|",
    ]
    for p in picks:
        row = [p.get("category", ""), p.get("copy", ""), p.get("structure", ""),
               p.get("title", ""), p.get("image_desc", ""), p.get("develop_note", "")]
        lines.append("| " + " | ".join(str(v).replace("|", "／").replace("\n", " ")
                                       for v in row) + " |")
    lines += ["", "## 후보 전체 (기대/증거/의문/공감 × 2)", "",
              "| 카테고리 | 문구 | 구조분석 | 심리 | 그림 |", "|---|---|---|---|---|"]
    for c in data.get("candidates", []):
        row = [c.get("category", ""), c.get("copy", ""), c.get("structure", ""),
               c.get("psychology", ""), c.get("image_desc", "")]
        lines.append("| " + " | ".join(str(v).replace("|", "／").replace("\n", " ")
                                       for v in row) + " |")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="내가 만들 영상 키워드/주제")
    ap.add_argument("--audience", default="초등 저학년 학부모")
    ap.add_argument("--benchmark-copy", default="", help="벤치마킹할 썸네일 문구 (시트의 '썸네일 문구' 칸)")
    ap.add_argument("--benchmark-url", default="", help="벤치마킹 영상 URL")
    ap.add_argument("--count", type=int, default=4, help="최종 픽 수 (기본 4 — 카테고리별 1)")
    ap.add_argument("--photos-dir", default="", help="소유 사진 폴더 (배경 1순위)")
    ap.add_argument("--out", default="thumbnail_out")
    ap.add_argument("--no-vault", action="store_true", help="볼트 05 리뷰/대기 저장 생략")
    args = ap.parse_args()

    out = Path(args.out)
    ensure_fonts()

    log(f"① 분석 + 문구 후보 생성: {args.topic}")
    data = generate_candidates(args.topic, args.audience,
                               args.benchmark_copy, args.benchmark_url)
    log(f"  후보 {len(data.get('candidates', []))}개")

    log("② 비평·디벨롭 → 최종 픽")
    picks = develop(args.topic, args.audience, data, args.count)
    for p in picks:
        log(f"  [{p.get('category','')}] {p.get('copy','')}")

    log("③ 렌더 (1280×720)")
    local_imgs = []
    if args.photos_dir:
        import glob as _glob
        local_imgs = sorted(g for ext in ("jpg", "jpeg", "png", "webp")
                            for g in _glob.glob(str(Path(args.photos_dir) / f"*.{ext}")))
        log(f"  로컬 사진 {len(local_imgs)}장 사용")
    render(picks, out, local_imgs)

    md = build_md(args.topic, args.audience, data, picks,
                  args.benchmark_copy, args.benchmark_url)
    (out / f"썸네일_{_file_token(args.topic)[:40] or '무제'}.md").write_text(md, encoding="utf-8")
    (out / "thumbnail_plan.json").write_text(
        json.dumps({"analysis": data.get("analysis", {}),
                    "candidates": data.get("candidates", []), "picks": picks},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_vault:
        name = save_to_review(args.topic, md)
        log(f"볼트 저장: 05 리뷰/대기/{name} (텔레그램 알림·답장 핑퐁은 orchestrator cron이 잇는다)")
    log(f"완료 → {out.resolve()}")


if __name__ == "__main__":
    main()
