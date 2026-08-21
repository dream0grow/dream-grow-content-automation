"""릴스(숏폼) 영상 자동 생성 — Open Generative AI(Muapi.ai) 연동

릴스 원고(`05 리뷰/대기/원고_릴스_*.md`)의 B-roll 장면 목록을 읽어 장면별
9:16 세로 영상 클립을 Muapi.ai(Open Generative AI가 쓰는 통합 게이트웨이)로
생성하고, ffmpeg로 이어 붙여 초벌 릴스 영상(reel_draft.mp4)을 만든다.
자막·내레이션·BGM은 notes.md에 정리해 두므로 캡컷 등에서 사람이 마무리한다.

사용법:
  python3 -m orchestrator.reels_video --script "원고_릴스_훈육_좋은+훈육....md"
      # 볼트 05 리뷰/대기의 파일명(부분 일치 가능) 또는 md 파일 경로
  python3 -m orchestrator.reels_video --topic "아이 훈육 3단계"
      # 원고 없이 주제만으로 장면 구성부터 생성
  python3 -m orchestrator.reels_video --script ... --dry-run
      # 장면·프롬프트만 뽑고 영상 API는 호출하지 않음 (키 불필요)

필요 시크릿: MUAPI_API_KEY (https://muapi.ai — Open Generative AI 설정 화면의 키와 동일)
모델/해상도/장면 수: DG_REELS_VIDEO_MODEL, DG_REELS_VIDEO_RESOLUTION, DG_REELS_MAX_SCENES
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import config
from orchestrator import llm

MUAPI_BASE = "https://api.muapi.ai/api/v1"
POLL_SECONDS = 4          # 폴링 간격 (테스트에서 monkeypatch)
POLL_TIMEOUT_MINUTES = 10  # 클립 1개 생성 대기 한도

REVIEW_DIR = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"


def log(msg: str) -> None:
    print(msg, flush=True)


def vault_root() -> Path:
    return Path(os.getenv("DG_VAULT_ROOT", str(config.PROJECT_ROOT / "vault")))


# ── 원고 찾기/파싱 ──────────────────────────────────────────────


def find_script(name: str) -> Path | None:
    """경로 또는 볼트 05 리뷰/대기의 파일명(부분 일치)으로 릴스 원고를 찾는다."""
    p = Path(name)
    if p.suffix == ".md" and p.exists():
        return p
    review = vault_root() / REVIEW_DIR
    if not review.exists():
        return None
    stem = name.removesuffix(".md")
    exact = review / f"{stem}.md"
    if exact.exists():
        return exact
    hits = sorted(f for f in review.glob("*.md") if stem in f.name)
    return hits[0] if hits else None


def parse_broll_table(md: str) -> list[dict]:
    """B-roll 장면 목록 표를 [{timecode, scene, keywords}]로 파싱한다.

    표 형식: | 타임코드 | 장면 | Pexels/Pixabay 키워드 (영어) | 대체 옵션 |
    (자체 제작) 표시 행은 영상 생성 대상이 아니므로 건너뛴다.
    """
    scenes = []
    in_table = False
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if "타임코드" in cells[0] or cells[1].strip() == "장면":
            in_table = True
            continue
        if set(cells[0]) <= set("-: "):  # 구분선
            continue
        if not in_table:
            continue
        timecode, scene, keywords = cells[0], cells[1], cells[2]
        if "자체 제작" in keywords or not keywords:
            continue
        kw = [k.strip() for k in keywords.replace("`", "").split(",") if k.strip()]
        scenes.append({"timecode": timecode, "scene": scene, "keywords": kw})
    return scenes


def parse_screen_directions(md: str) -> list[dict]:
    """B-roll 표가 없을 때 *(화면: ...)* 연출 지시를 장면 목록으로 쓴다."""
    scenes = []
    for m in re.finditer(r"\(화면\s*[:：]\s*(.+?)\)", md):
        desc = m.group(1).strip().strip("*").strip()
        if desc and "리드마그넷" not in desc:
            scenes.append({"timecode": "", "scene": desc, "keywords": []})
    return scenes


def extract_narration(md: str) -> str:
    """따옴표로 시작하는 내레이션 줄만 모아 캡컷 자막 재료로 넘긴다."""
    lines = []
    for line in md.splitlines():
        s = line.strip().strip("*").strip()
        if s.startswith('"') or s.startswith("“"):
            lines.append(s.strip('"“”'))
    return "\n".join(lines)


# ── 장면 → 영상 프롬프트 ─────────────────────────────────────────

SCENE_PROMPT = """다음은 초등 학부모 대상 인스타그램 릴스의 B-roll 장면 목록이다.
각 장면을 text-to-video AI 모델에 넣을 영어 프롬프트 한 문장으로 바꿔라.

규칙:
- 실사(cinematic, realistic) 세로 영상. 한국 가정/교실 맥락이면 Korean family, Korean classroom을 명시.
- 화면 안에 글자·자막·로고가 나오지 않게 "no text, no captions" 포함.
- 인물은 자연스러운 일상 연기. 과장된 표정·연출 금지.
- 각 프롬프트는 60단어 이내.

장면 목록:
{scenes}

JSON으로만 답하라: {{"prompts": ["...", ...]}} (장면 순서 그대로, 개수 동일)"""

TOPIC_SCENES_PROMPT = """초등 학부모 대상 인스타그램 릴스(45초)의 B-roll 장면을 설계하라.
주제: {topic}

장면 {count}개를 순서대로 만들고, 각 장면마다 text-to-video AI에 넣을 영어 프롬프트를 써라.
규칙: 실사 세로 영상, 한국 가정/교실 맥락(Korean family 등 명시), "no text, no captions" 포함, 60단어 이내.

JSON으로만 답하라:
{{"scenes": [{{"scene": "장면 설명(한국어)", "prompt": "영어 프롬프트"}}, ...]}}"""


def _fallback_prompt(scene: dict) -> str:
    base = ", ".join(scene["keywords"][:2]) or scene["scene"]
    return (
        f"{base}, cinematic realistic vertical video, Korean family context, "
        "natural lighting, no text, no captions"
    )


def build_prompts(scenes: list[dict], use_llm: bool = True) -> list[str]:
    """장면 목록을 영어 t2v 프롬프트로 변환한다. LLM 실패 시 키워드 폴백."""
    if use_llm:
        listing = "\n".join(
            f"{i+1}. [{s['timecode']}] {s['scene']}"
            + (f" (키워드: {', '.join(s['keywords'])})" if s["keywords"] else "")
            for i, s in enumerate(scenes)
        )
        try:
            data = llm.call_json(SCENE_PROMPT.format(scenes=listing))
            prompts = data.get("prompts") or []
            if len(prompts) == len(scenes):
                return [str(p) for p in prompts]
            log(f"⚠️ LLM 프롬프트 수 불일치({len(prompts)}/{len(scenes)}) — 키워드 폴백")
        except Exception as e:  # LLM 없이도 동작해야 한다
            log(f"⚠️ LLM 프롬프트 변환 실패({e}) — 키워드 폴백")
    return [_fallback_prompt(s) for s in scenes]


def scenes_from_topic(topic: str, count: int) -> list[dict]:
    """원고 없이 주제만으로 장면+프롬프트를 설계한다 (LLM 필수)."""
    data = llm.call_json(TOPIC_SCENES_PROMPT.format(topic=topic, count=count))
    out = []
    for s in data.get("scenes", [])[:count]:
        if s.get("prompt"):
            out.append({
                "timecode": "", "scene": s.get("scene", ""), "keywords": [],
                "prompt": s["prompt"],
            })
    if not out:
        raise RuntimeError("주제 기반 장면 설계 실패 — LLM 응답에 scenes 없음")
    return out


# ── Muapi.ai 클라이언트 (Open Generative AI와 동일 프로토콜) ─────


def _api_key() -> str:
    key = config.MUAPI_API_KEY
    if not key:
        raise RuntimeError(
            "MUAPI_API_KEY가 없습니다. docs/open-generative-ai-setup.md를 따라 "
            "muapi.ai 키를 발급해 GitHub Secrets에 등록하세요."
        )
    return key


def submit_video(prompt: str, model: str, resolution: str, duration: int) -> str:
    """생성 작업을 제출하고 request_id를 반환한다."""
    resp = requests.post(
        f"{MUAPI_BASE}/{model}",
        headers={"Content-Type": "application/json", "x-api-key": _api_key()},
        json={
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "duration": duration,
            "resolution": resolution,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Muapi 제출 실패 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    rid = data.get("request_id") or data.get("id")
    if not rid:
        raise RuntimeError(f"Muapi 응답에 request_id 없음: {str(data)[:200]}")
    return rid


def poll_result(request_id: str) -> str:
    """완료까지 폴링하고 결과 영상 URL을 반환한다."""
    deadline = time.time() + POLL_TIMEOUT_MINUTES * 60
    url = f"{MUAPI_BASE}/predictions/{request_id}/result"
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        resp = requests.get(
            url, headers={"x-api-key": _api_key()}, timeout=60)
        if resp.status_code >= 500:
            continue
        resp.raise_for_status()
        data = resp.json()
        status = str(data.get("status", "")).lower()
        if status in ("completed", "succeeded", "success"):
            video = (data.get("outputs") or [None])[0] or data.get("url") \
                or (data.get("output") or {}).get("url")
            if not video:
                raise RuntimeError(f"완료됐지만 영상 URL 없음: {str(data)[:200]}")
            return video
        if status in ("failed", "error"):
            raise RuntimeError(f"생성 실패: {data.get('error') or status}")
    raise RuntimeError(f"생성 시간 초과({POLL_TIMEOUT_MINUTES}분): {request_id}")


def download(url: str, out_path: Path) -> Path:
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    return out_path


def generate_clip(prompt: str, out_path: Path, model: str = "",
                  resolution: str = "", duration: int = 0) -> Path:
    model = model or config.REELS_VIDEO_MODEL
    resolution = resolution or config.REELS_VIDEO_RESOLUTION
    duration = duration or config.REELS_SCENE_SECONDS
    rid = submit_video(prompt, model, resolution, duration)
    log(f"  요청 접수 request_id={rid} — 생성 대기…")
    return download(poll_result(rid), out_path)


# ── 합본 ────────────────────────────────────────────────────────


def merge_command(clips: list[Path], out: Path) -> list[str]:
    """클립들을 1080x1920로 통일해 이어 붙이는 ffmpeg 명령을 만든다(무음)."""
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", str(c)]
    parts = []
    for i in range(len(clips)):
        parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30[v{i}]")
    concat_in = "".join(f"[v{i}]" for i in range(len(clips)))
    parts.append(f"{concat_in}concat=n={len(clips)}:v=1:a=0[v]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    return cmd


def merge_clips(clips: list[Path], out: Path) -> Path | None:
    if not clips:
        return None
    if shutil.which("ffmpeg") is None:
        log("⚠️ ffmpeg 없음 — 합본 생략 (클립 개별 파일만 저장)")
        return None
    subprocess.run(merge_command(clips, out), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


# ── 산출물 정리 ─────────────────────────────────────────────────


def write_notes(out_dir: Path, source: str, scenes: list[dict],
                narration: str, merged: Path | None,
                dry_run: bool = False) -> Path:
    lines = [
        "# 릴스 초벌 영상 노트",
        "",
        f"- 원고: {source}",
        "- 합본: " + (merged.name if merged else (
            "(dry-run — 영상 미생성)" if dry_run
            else "(ffmpeg 없음 — scene_*.mp4를 직접 이어 붙이세요)")),
        f"- 모델: {config.REELS_VIDEO_MODEL} / 9:16 / {config.REELS_VIDEO_RESOLUTION}",
        "",
        "AI가 만든 건 B-roll 배경 영상뿐이다. 자막·내레이션·BGM·리드마그넷 화면은",
        "캡컷에서 아래 재료로 얹어 마무리한다.",
        "",
        "## 장면",
        "",
        "| # | 타임코드 | 장면 | 클립 | 프롬프트 |",
        "|---|---------|------|------|----------|",
    ]
    for i, s in enumerate(scenes):
        clip = s.get("clip") or ("(dry-run 미생성)" if dry_run else "(실패)")
        lines.append(
            f"| {i+1} | {s.get('timecode','')} | {s['scene']} | {clip} "
            f"| {s.get('prompt','')} |")
    if narration:
        lines += ["", "## 내레이션(자막 재료)", "", narration]
    path = out_dir / "notes.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(script: str = "", topic: str = "", out_dir: str = "reels_out",
        max_scenes: int = 0, dry_run: bool = False, use_llm: bool = True) -> dict:
    max_scenes = max_scenes or config.REELS_MAX_SCENES
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    narration = ""
    if script:
        path = find_script(script)
        if not path:
            raise SystemExit(f"릴스 원고를 찾지 못함: {script}")
        source = path.name
        md = path.read_text(encoding="utf-8")
        scenes = parse_broll_table(md) or parse_screen_directions(md)
        if not scenes:
            raise SystemExit("원고에서 B-roll 표/화면 지시를 찾지 못함")
        scenes = scenes[:max_scenes]
        narration = extract_narration(md)
        log(f"📄 원고: {source} — 장면 {len(scenes)}개")
        prompts = build_prompts(scenes, use_llm=use_llm)
        for s, p in zip(scenes, prompts):
            s["prompt"] = p
    elif topic:
        source = f"(주제) {topic}"
        scenes = scenes_from_topic(topic, max_scenes)
        log(f"💡 주제 기반 장면 {len(scenes)}개 설계")
    else:
        raise SystemExit("--script 또는 --topic 중 하나가 필요합니다")

    merged = None
    if dry_run:
        log("🧪 dry-run — 영상 생성 생략, 장면/프롬프트만 저장")
    else:
        clips = []
        for i, s in enumerate(scenes):
            log(f"🎬 [{i+1}/{len(scenes)}] {s['scene'][:40]}")
            clip_path = out / f"scene_{i+1:02d}.mp4"
            try:
                generate_clip(s["prompt"], clip_path)
                s["clip"] = clip_path.name
                clips.append(clip_path)
            except Exception as e:
                s["error"] = str(e)
                log(f"  ⚠️ 실패: {e}")
        if not clips:
            raise SystemExit("생성된 클립이 없습니다 (MUAPI_API_KEY/모델 확인)")
        merged = merge_clips(clips, out / "reel_draft.mp4")
        if merged:
            log(f"✅ 합본 완성: {merged}")

    plan = {
        "source": source,
        "model": config.REELS_VIDEO_MODEL,
        "resolution": config.REELS_VIDEO_RESOLUTION,
        "scene_seconds": config.REELS_SCENE_SECONDS,
        "scenes": scenes,
        "merged": merged.name if merged else None,
        "dry_run": dry_run,
    }
    (out / "reels_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_notes(out, source, scenes, narration, merged, dry_run=dry_run)
    log(f"📦 산출물: {out}/ (reels_plan.json, notes.md"
        + (", scene_*.mp4" if not dry_run else "") + ")")
    return plan


def main() -> None:
    ap = argparse.ArgumentParser(description="릴스 원고 → 장면별 AI 영상 → 초벌 릴스")
    ap.add_argument("--script", default="", help="릴스 원고 파일명(05 리뷰/대기, 부분 일치) 또는 경로")
    ap.add_argument("--topic", default="", help="원고 없이 주제만으로 생성")
    ap.add_argument("--out", default="reels_out", help="산출물 폴더 (기본 reels_out)")
    ap.add_argument("--max-scenes", type=int, default=0,
                    help=f"최대 장면 수 (기본 DG_REELS_MAX_SCENES={config.REELS_MAX_SCENES})")
    ap.add_argument("--dry-run", action="store_true", help="프롬프트만 뽑고 영상 API 호출 안 함")
    ap.add_argument("--no-llm", action="store_true", help="LLM 없이 키워드로 프롬프트 구성")
    args = ap.parse_args()
    run(script=args.script, topic=args.topic, out_dir=args.out,
        max_scenes=args.max_scenes, dry_run=args.dry_run, use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
