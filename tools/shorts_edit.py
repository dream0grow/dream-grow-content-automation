"""쇼츠 자동 편집 — DJI 오즈모 나노 등 촬영 원본을 초벌 쇼츠 MP4로 만든다.

로컬(맥/윈도우) 전용. 클라우드에 원본을 올리지 않는다.
파이프라인: 오디오 분석(무음/박수) → 컷 계획 → 조각 렌더 → 합본 → Whisper 자막 → 자막 굽기.

  전체 실행:   python3 tools/shorts_edit.py 촬영본.mp4
  폴더 일괄:   python3 tools/shorts_edit.py SD카드폴더/
  계획만 확인: python3 tools/shorts_edit.py 촬영본.mp4 --mode analyze
  조각 렌더:   python3 tools/shorts_edit.py 촬영본.mp4 --mode render --segment 0
             (Cowork 45초 bash 제한 대응 — 세그먼트 하나씩 렌더)
  이후 단계:   --mode concat / subs / burn

편집 규칙 (video-lecture-editor 스킬과 동일 철학):
- 무음 구간 제거, 앞뒤 여유(--pad, 기본 0.3초)는 남긴다.
- 박수 소리 = 재촬영(NG) 표시 → 박수 직전 테이크를 잘라낸다 (--no-clap로 끔).
- 색 보정 없음 — 원본 화질 그대로, 9:16(1080x1920) 변환만 한다.

필요 도구: ffmpeg/ffprobe (PATH). 자막은 faster-whisper(권장) 또는 whisper CLI.
없으면 자막 단계만 건너뛰고 안내를 남긴다. 설치는 docs/shorts-edit-setup.md 참고.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from array import array
from pathlib import Path

try:  # 있으면 빠르고, 없어도 동작한다
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv"}
SAMPLE_RATE = 16000
WIN_SEC = 0.05  # RMS 창 크기(초)
DB_FLOOR = -90.0


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- ffmpeg 유틸

def require_ffmpeg() -> None:
    for exe in ("ffmpeg", "ffprobe"):
        if shutil.which(exe) is None:
            raise SystemExit(
                f"❌ {exe}를 찾을 수 없습니다. docs/shorts-edit-setup.md의 설치 안내를 따라주세요.\n"
                "   (Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg)")


def probe(video: Path) -> dict:
    """폭/높이/길이/fps를 ffprobe로 읽는다."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(video)],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    vstream = next(s for s in info["streams"] if s.get("codec_type") == "video")
    fps = 30.0
    if vstream.get("avg_frame_rate") and vstream["avg_frame_rate"] != "0/0":
        num, den = vstream["avg_frame_rate"].split("/")
        if float(den):
            fps = float(num) / float(den)
    return {
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "duration": float(info["format"]["duration"]),
        "fps": round(fps, 3),
    }


def decode_pcm(video: Path) -> bytes:
    """모노 16kHz s16le PCM으로 디코드 (분석용)."""
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn",
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout


# ------------------------------------------------------------- 오디오 분석

def rms_envelope(pcm: bytes, sample_rate: int = SAMPLE_RATE,
                 win_sec: float = WIN_SEC) -> list[float]:
    """창별 RMS를 dBFS 리스트로 (창 하나 = win_sec초)."""
    win = max(1, int(sample_rate * win_sec))
    if _np is not None:
        samples = _np.frombuffer(pcm, dtype=_np.int16).astype(_np.float64)
        n = len(samples) // win
        if n == 0:
            return []
        chunks = samples[: n * win].reshape(n, win)
        rms = _np.sqrt((chunks ** 2).mean(axis=1))
        with _np.errstate(divide="ignore"):
            db = 20 * _np.log10(rms / 32768.0)
        return [float(max(v, DB_FLOOR)) if math.isfinite(v) else DB_FLOOR for v in db]
    samples = array("h")
    samples.frombytes(pcm[: (len(pcm) // 2) * 2])
    env = []
    for i in range(0, len(samples) - win + 1, win):
        acc = 0
        for s in samples[i:i + win]:
            acc += s * s
        rms = math.sqrt(acc / win)
        env.append(20 * math.log10(rms / 32768.0) if rms > 0 else DB_FLOOR)
    return env


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    """True 연속 구간을 [시작, 끝) 인덱스 쌍으로."""
    runs, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return runs


def speech_segments(env_db: list[float], *, win_sec: float = WIN_SEC,
                    silence_db: float = -35.0, min_silence: float = 0.9,
                    pad: float = 0.3, min_speech: float = 0.3,
                    total: float | None = None) -> list[list[float]]:
    """무음을 걷어낸 발화 구간 [start, end] 목록(초).

    min_silence보다 짧은 무음은 발화에 붙여 두고(호흡 유지),
    잘라낸 자리에는 앞뒤 pad초를 남긴다.
    """
    if not env_db:
        return []
    total = total if total is not None else len(env_db) * win_sec
    loud = [db > silence_db for db in env_db]
    raw = [[a * win_sec, b * win_sec] for a, b in _runs(loud)]
    # 짧은 무음으로 갈라진 발화는 병합
    merged: list[list[float]] = []
    for seg in raw:
        if merged and seg[0] - merged[-1][1] < min_silence:
            merged[-1][1] = seg[1]
        else:
            merged.append(list(seg))
    kept = [s for s in merged if s[1] - s[0] >= min_speech]
    # 앞뒤 여유를 남기고 경계 클램프 + 겹침 병합
    padded: list[list[float]] = []
    for s, e in kept:
        s, e = max(0.0, s - pad), min(total, e + pad)
        if padded and s <= padded[-1][1]:
            padded[-1][1] = max(padded[-1][1], e)
        else:
            padded.append([s, e])
    return padded


def detect_claps(env_db: list[float], *, win_sec: float = WIN_SEC,
                 clap_db: float = -6.0, max_len: float = 0.4,
                 min_gap: float = 0.8) -> list[float]:
    """박수(짧고 아주 큰 소리) 시각 목록(초). 오탐은 dry-run 계획에서 사람이 거른다."""
    loud = [db > clap_db for db in env_db]
    claps: list[float] = []
    for a, b in _runs(loud):
        if (b - a) * win_sec <= max_len:
            t = a * win_sec
            if not claps or t - claps[-1] >= min_gap:
                claps.append(round(t, 2))
    return claps


def apply_claps(segments: list[list[float]], claps: list[float], *,
                cut_after: float = 0.2, min_speech: float = 0.3) -> list[list[float]]:
    """박수 = NG 표시: 박수 '직전 테이크'를 잘라낸다.

    - 박수가 발화 구간 안이면: 그 구간의 시작~박수+cut_after를 제거, 남은 뒤쪽만 유지.
    - 박수가 무음 구간이면: 바로 앞 발화 구간 전체를 제거.
    """
    result = [list(s) for s in segments]
    for t in claps:
        inside = None
        for seg in result:
            if seg[0] <= t <= seg[1]:
                inside = seg
                break
        if inside is not None:
            new_start = t + cut_after
            if inside[1] - new_start >= min_speech:
                inside[0] = new_start
            else:
                result.remove(inside)
        else:
            prev = [seg for seg in result if seg[1] < t]
            if prev:
                result.remove(prev[-1])
    return result


# ------------------------------------------------------------- 세로 변환/렌더

def vertical_filter(width: int, height: int, fit: str = "crop") -> str:
    """9:16(1080x1920) 변환 ffmpeg 필터. crop=중앙 크롭, blur=블러 배경 레터박스."""
    if fit == "blur":
        return ("split[a][b];"
                "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=24[bg];"
                "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2")
    if width * 16 > height * 9:  # 원본이 9:16보다 가로로 넓음 → 좌우 크롭
        crop = "crop=ih*9/16:ih"
    else:  # 9:16보다 세로로 김 → 상하 크롭
        crop = "crop=iw:iw*16/9"
    return f"{crop},scale=1080:1920,setsar=1"


def segment_cmd(video: Path, seg: list[float], out: Path, vfilter: str) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error",
            "-ss", f"{seg[0]:.3f}", "-to", f"{seg[1]:.3f}", "-i", str(video),
            "-vf", vfilter, "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]


def concat_cmd(list_file: Path, out: Path) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", "-movflags", "+faststart", str(out)]


def sub_filter_path(p: Path) -> str:
    """subtitles 필터용 경로 이스케이프 (윈도우 드라이브 콜론 포함)."""
    s = str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return s


def burn_cmd(video: Path, srt: Path, out: Path, *, font: str = "Pretendard",
             size: int = 15) -> list[str]:
    style = (f"FontName={font},Fontsize={size},Bold=1,"
             "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "Outline=2,Shadow=0,Alignment=2,MarginV=70")
    vf = f"subtitles='{sub_filter_path(srt)}':force_style='{style}'"
    return ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart", str(out)]


# ------------------------------------------------------------------- 자막

def srt_timestamp(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(entries: list[tuple[float, float, str]]) -> str:
    lines = []
    for i, (start, end, text) in enumerate(entries, 1):
        lines.append(f"{i}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text.strip()}\n")
    return "\n".join(lines)


def transcribe(media: Path, *, model: str = "small",
               language: str = "ko") -> list[tuple[float, float, str]] | None:
    """faster-whisper → whisper CLI 순서로 시도. 둘 다 없으면 None."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
        wm = WhisperModel(model, compute_type="int8")
        segments, _ = wm.transcribe(str(media), language=language, vad_filter=True)
        return [(s.start, s.end, s.text) for s in segments]
    except ImportError:
        pass
    if shutil.which("whisper"):
        outdir = media.parent
        subprocess.run(
            ["whisper", str(media), "--model", model, "--language", language,
             "--output_format", "json", "--output_dir", str(outdir)],
            check=True, capture_output=True)
        data = json.loads((outdir / f"{media.stem}.json").read_text(encoding="utf-8"))
        return [(s["start"], s["end"], s["text"]) for s in data["segments"]]
    return None


# ------------------------------------------------------------------- 단계

def out_dir_for(video: Path, out: str | None) -> Path:
    d = Path(out) if out else video.parent / f"{video.stem}_shorts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def analyze(video: Path, outdir: Path, args) -> dict:
    log(f"🔍 분석: {video.name}")
    info = probe(video)
    env = rms_envelope(decode_pcm(video))
    segs = speech_segments(env, silence_db=args.silence_db, min_silence=args.min_silence,
                           pad=args.pad, total=info["duration"])
    claps = [] if args.no_clap else detect_claps(env, clap_db=args.clap_db)
    final = apply_claps(segs, claps) if claps else segs
    kept = sum(e - s for s, e in final)
    plan = {
        "input": str(video), "probe": info,
        "params": {"silence_db": args.silence_db, "min_silence": args.min_silence,
                   "pad": args.pad, "clap_db": args.clap_db, "no_clap": args.no_clap,
                   "fit": args.fit},
        "claps": claps, "segments": [[round(s, 3), round(e, 3)] for s, e in final],
        "duration_in": round(info["duration"], 2), "duration_out": round(kept, 2),
    }
    plan_path = outdir / "edit_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  원본 {plan['duration_in']}초 → 편집 후 {plan['duration_out']}초, "
        f"세그먼트 {len(final)}개, 박수(NG) {len(claps)}건")
    for i, (s, e) in enumerate(plan["segments"]):
        log(f"  [{i}] {s:8.2f} ~ {e:8.2f}  ({e - s:.2f}초)")
    if claps:
        log(f"  👏 박수 감지: {', '.join(f'{t}s' for t in claps)} — 오탐이면 --no-clap로 재실행")
    if kept > 180:
        log("  ⚠️ 180초 초과 — 쇼츠 한도를 넘습니다. 여러 편으로 나누는 걸 권장합니다.")
    log(f"  계획 저장: {plan_path}")
    return plan


def load_plan(outdir: Path) -> dict:
    plan_path = outdir / "edit_plan.json"
    if not plan_path.exists():
        raise SystemExit(f"❌ {plan_path} 없음 — 먼저 --mode analyze를 실행하세요.")
    return json.loads(plan_path.read_text(encoding="utf-8"))


def render(video: Path, outdir: Path, args, plan: dict, only: int | None = None) -> None:
    vfilter = vertical_filter(plan["probe"]["width"], plan["probe"]["height"], args.fit)
    segs = plan["segments"]
    targets = [only] if only is not None else range(len(segs))
    for i in targets:
        seg_out = outdir / f"seg_{i:03d}.mp4"
        log(f"🎬 렌더 [{i}] {segs[i][0]:.2f}~{segs[i][1]:.2f} → {seg_out.name}")
        subprocess.run(segment_cmd(video, segs[i], seg_out, vfilter), check=True)


def concat(outdir: Path, plan: dict) -> Path:
    missing = [i for i in range(len(plan["segments"]))
               if not (outdir / f"seg_{i:03d}.mp4").exists()]
    if missing:
        raise SystemExit(f"❌ 미렌더 세그먼트 {missing} — --mode render를 먼저 완료하세요.")
    list_file = outdir / "concat.txt"
    list_file.write_text(
        "".join(f"file '{(outdir / f'seg_{i:03d}.mp4').name}'\n"
                for i in range(len(plan["segments"]))), encoding="utf-8")
    cut = outdir / "cut.mp4"
    subprocess.run(concat_cmd(list_file, cut), check=True)
    log(f"✂️ 합본 완료: {cut}")
    return cut


def subs(outdir: Path, args) -> Path | None:
    cut = outdir / "cut.mp4"
    if not cut.exists():
        raise SystemExit("❌ cut.mp4 없음 — --mode concat까지 먼저 실행하세요.")
    log(f"📝 자막 생성(Whisper {args.whisper_model}, {args.language})…")
    entries = transcribe(cut, model=args.whisper_model, language=args.language)
    if entries is None:
        log("⚠️ Whisper 미설치 — 자막 생략. 설치: pip install faster-whisper "
            "(docs/shorts-edit-setup.md)")
        return None
    srt = outdir / "subtitles.srt"
    srt.write_text(to_srt(entries), encoding="utf-8")
    log(f"  자막 {len(entries)}줄 → {srt}")
    return srt


def burn(outdir: Path, args) -> Path:
    cut, srt = outdir / "cut.mp4", outdir / "subtitles.srt"
    if not srt.exists():
        raise SystemExit("❌ subtitles.srt 없음 — --mode subs를 먼저 실행하세요.")
    final = outdir / "final.mp4"
    subprocess.run(burn_cmd(cut, srt, final, font=args.sub_font, size=args.sub_size),
                   check=True)
    log(f"🔥 자막 굽기 완료: {final}")
    return final


def write_notes(outdir: Path, plan: dict, final: Path | None) -> None:
    claps = plan.get("claps") or []
    lines = [
        f"# 쇼츠 편집 노트 — {Path(plan['input']).name}", "",
        f"- 원본 {plan['duration_in']}초 → 편집 후 {plan['duration_out']}초",
        f"- 세그먼트 {len(plan['segments'])}개, 박수(NG) 컷 {len(claps)}건"
        + (f" ({', '.join(f'{t}s' for t in claps)})" if claps else ""),
        f"- 결과물: {final.name if final else 'cut.mp4 (자막 없음)'} / subtitles.srt / edit_plan.json",
        "", "## 마무리(캡컷) 재료",
        "- 자막 문구 수정은 subtitles.srt 고친 뒤 `--mode burn` 재실행",
        "- 후킹 자막·BGM·효과음은 캡컷에서 final.mp4 위에 얹기",
        "- 컷이 마음에 안 들면 edit_plan.json의 segments를 손보고 `--mode render` 재실행",
    ]
    (outdir / "notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def process(video: Path, args) -> None:
    outdir = out_dir_for(video, args.out)
    plan = analyze(video, outdir, args)
    if args.mode == "analyze":
        return
    render(video, outdir, args, plan)
    concat(outdir, plan)
    srt = subs(outdir, args)
    final = burn(outdir, args) if srt else None
    write_notes(outdir, plan, final)
    log(f"✅ 완료: {final or (outdir / 'cut.mp4')}")


def main(argv: list[str] | None = None) -> None:
    if sys.platform == "win32":  # 콘솔 cp949 깨짐 방지
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="쇼츠 자동 편집 (무음/NG 컷 + 9:16 + 자막)")
    ap.add_argument("input", help="영상 파일 또는 폴더")
    ap.add_argument("--out", help="출력 폴더 (기본: <영상명>_shorts/)")
    ap.add_argument("--mode", default="all",
                    choices=["all", "analyze", "render", "concat", "subs", "burn"])
    ap.add_argument("--segment", type=int, help="render 모드에서 특정 세그먼트만")
    ap.add_argument("--pad", type=float, default=0.3, help="컷 앞뒤 여유(초, 기본 0.3)")
    ap.add_argument("--min-silence", type=float, default=0.9,
                    help="이보다 긴 무음만 잘라냄(초, 기본 0.9)")
    ap.add_argument("--silence-db", type=float, default=-35.0, help="무음 판정 dBFS")
    ap.add_argument("--clap-db", type=float, default=-6.0, help="박수 판정 dBFS")
    ap.add_argument("--no-clap", action="store_true", help="박수 NG 컷 비활성화")
    ap.add_argument("--fit", default="crop", choices=["crop", "blur"],
                    help="9:16 변환 방식 (crop=중앙 크롭, blur=블러 배경)")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--sub-font", default="Pretendard")
    ap.add_argument("--sub-size", type=int, default=15)
    args = ap.parse_args(argv)

    require_ffmpeg()
    target = Path(args.input)
    if target.is_dir():
        videos = sorted(p for p in target.iterdir() if p.suffix.lower() in VIDEO_EXTS)
        if not videos:
            raise SystemExit(f"❌ {target}에 영상 파일이 없습니다.")
        if args.mode not in ("all", "analyze"):
            raise SystemExit("❌ 폴더 입력은 --mode all/analyze만 지원합니다.")
        log(f"📂 {len(videos)}개 영상 일괄 처리")
        for v in videos:
            process(v, args)
        return
    if not target.exists():
        raise SystemExit(f"❌ 파일 없음: {target}")

    outdir = out_dir_for(target, args.out)
    if args.mode in ("all", "analyze"):
        process(target, args)
    elif args.mode == "render":
        plan = load_plan(outdir)
        render(target, outdir, args, plan, only=args.segment)
    elif args.mode == "concat":
        concat(outdir, load_plan(outdir))
    elif args.mode == "subs":
        subs(outdir, args)
    elif args.mode == "burn":
        burn(outdir, args)
        write_notes(outdir, load_plan(outdir), outdir / "final.mp4")


if __name__ == "__main__":
    main()
