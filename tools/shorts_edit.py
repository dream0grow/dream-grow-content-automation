"""쇼츠 자동 편집 — DJI 오즈모 나노 등 촬영 원본을 초벌 쇼츠 MP4로 만든다.

로컬(맥/윈도우) 전용. 클라우드에 원본을 올리지 않는다.
파이프라인: 오디오 분석(무음/박수) → 컷 계획 → 조각 렌더 → 합본 → Whisper 자막
          → 스타일 프리셋(ASS) 자막 굽기 (+ 상단 후킹 자막).

  전체 실행:   python3 tools/shorts_edit.py 촬영본.mp4
  이름만으로:  python3 tools/shorts_edit.py DJI_20260914072454_0008_D --source-dir "<촬영본 폴더>"
             (확장자 없이 이름만 주면 폴더(또는 DG_OSMO_DIR)에서 MP4를 찾는다. LRF/WAV 무시)
  폴더 일괄:   python3 tools/shorts_edit.py SD카드폴더/
  계획만 확인: python3 tools/shorts_edit.py 촬영본.mp4 --mode analyze
  조각 렌더:   python3 tools/shorts_edit.py 촬영본.mp4 --mode render --segment 0
             (Cowork 45초 bash 제한 대응 — 세그먼트 하나씩 렌더)
  이후 단계:   --mode concat / subs / burn
  자막 스타일: --style growcircle (기본, data/shorts_styles/*.json) --hook "상단 후킹 문구"

편집 규칙 (video-lecture-editor 스킬과 동일 철학):
- 무음 구간 제거, 앞뒤 여유(--pad, 기본 0.3초)는 남긴다.
- 박수 소리 = 재촬영(NG) 표시 → 박수 직전 테이크를 잘라낸다 (--no-clap로 끔).
- 색 보정 없음 — 원본 화질 그대로, 9:16(1080x1920) 변환만 한다.

자막 규칙:
- Whisper 결과를 프리셋의 max_chars 기준으로 짧게 끊어(쇼츠식 큰 자막) ASS로 굽는다.
- subtitles.srt에서 `==단어==`로 감싼 부분은 프리셋의 highlight_color(노란색 등)로 강조된다.
  (썸네일 스킬의 =="강조"== 관례와 같다.) --highlight 단어,단어 로 자동 강조도 가능.
- --hook "문구" 는 화면 상단에 큰 제목 자막을 얹는다(`|`로 줄바꿈, --hook-seconds로 노출 시간).

필요 도구: ffmpeg (PATH 또는 `pip install imageio-ffmpeg`). ffprobe가 없으면 ffmpeg로 대신 읽는다.
자막은 faster-whisper(권장) 또는 whisper CLI. 없으면 자막 단계만 건너뛴다.
설치는 docs/shorts-edit-setup.md 참고.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from array import array
from pathlib import Path

try:  # 있으면 빠르고, 없어도 동작한다
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv"}  # DJI의 .LRF(저해상 프록시)·.WAV는 자동 제외
SAMPLE_RATE = 16000
WIN_SEC = 0.05  # RMS 창 크기(초)
DB_FLOOR = -90.0
OUT_W, OUT_H = 1080, 1920

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLE_DIR = REPO_ROOT / "data" / "shorts_styles"
FONTS_DIR = REPO_ROOT / "data" / "fonts"  # 여기에 otf/ttf를 넣으면 설치 없이 자막에 쓴다
DEFAULT_STYLE = "growcircle"

FFMPEG = "ffmpeg"
FFPROBE: str | None = "ffprobe"


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- ffmpeg 유틸

def find_ffmpeg() -> tuple[str, str | None]:
    """ffmpeg/ffprobe 경로. PATH에 없으면 imageio-ffmpeg 동봉 바이너리로 폴백(ffprobe는 없을 수 있음)."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None:
        try:
            import imageio_ffmpeg  # type: ignore
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg = None
    if ffmpeg is None:
        raise SystemExit(
            "❌ ffmpeg를 찾을 수 없습니다. docs/shorts-edit-setup.md의 설치 안내를 따라주세요.\n"
            "   (Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg / "
            "또는 pip install imageio-ffmpeg)")
    return ffmpeg, ffprobe


def require_ffmpeg() -> None:
    global FFMPEG, FFPROBE
    FFMPEG, FFPROBE = find_ffmpeg()


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VID_RE = re.compile(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b.*?(?:,\s*([\d.]+)\s*fps)?")


def parse_ffmpeg_info(stderr: str) -> dict:
    """`ffmpeg -i` 출력에서 폭/높이/길이/fps를 뽑는다 (ffprobe 없을 때 폴백)."""
    m = _DUR_RE.search(stderr)
    duration = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 0.0
    v = _VID_RE.search(stderr)
    if not v:
        raise RuntimeError("영상 스트림 정보를 읽지 못했습니다.")
    fps = float(v.group(3)) if v.group(3) else 30.0
    return {"width": int(v.group(1)), "height": int(v.group(2)),
            "duration": duration, "fps": round(fps, 3)}


def probe(video: Path) -> dict:
    """폭/높이/길이/fps. ffprobe가 있으면 JSON으로, 없으면 ffmpeg -i 출력을 파싱한다."""
    if FFPROBE:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json",
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
    res = subprocess.run([FFMPEG, "-hide_banner", "-i", str(video)],
                         capture_output=True, text=True)
    return parse_ffmpeg_info(res.stderr)


def decode_pcm(video: Path) -> bytes:
    """모노 16kHz s16le PCM으로 디코드 (분석용)."""
    return subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(video), "-vn",
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
    return [FFMPEG, "-y", "-v", "error",
            "-ss", f"{seg[0]:.3f}", "-to", f"{seg[1]:.3f}", "-i", str(video),
            "-vf", vfilter, "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]


def concat_cmd(list_file: Path, out: Path) -> list[str]:
    return [FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", "-movflags", "+faststart", str(out)]


def sub_filter_path(p: Path) -> str:
    """subtitles/ass 필터용 경로 이스케이프 (윈도우 드라이브 콜론 포함)."""
    s = str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return s


def burn_cmd(video: Path, ass: Path, out: Path, *, fonts_dir: Path | None = None) -> list[str]:
    """ASS 자막을 굽는 ffmpeg 명령. fonts_dir가 있으면 설치 없이 그 폴더의 폰트를 쓴다."""
    vf = f"ass='{sub_filter_path(ass)}'"
    if fonts_dir is not None:
        vf += f":fontsdir='{sub_filter_path(fonts_dir)}'"
    return [FFMPEG, "-y", "-v", "error", "-i", str(video), "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart", str(out)]


# ------------------------------------------------------------- 자막 스타일

PLAIN_STYLE = {
    "name": "plain",
    "font": "Pretendard",
    "font_fallbacks": ["Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic",
                       "Noto Sans CJK KR", "WenQuanYi Zen Hei"],
    "size": 64, "bold": True,
    "color": "#FFFFFF", "outline_color": "#000000", "outline": 4, "shadow": 0,
    "highlight_color": "#FFE100",
    "box": False, "box_color": "#000000", "box_alpha": 0.55,
    "align": "bottom", "margin_v": 360, "margin_h": 60,
    "spacing": 0, "max_chars": 16, "max_lines": 2,
    "hook": {"size": 84, "color": "#FFFFFF", "outline_color": "#000000", "outline": 6,
             "shadow": 0, "highlight_color": "#FFE100", "box": False,
             "align": "top", "margin_v": 300, "margin_h": 60},
}


def load_style(name_or_path: str | None) -> dict:
    """프리셋 이름(data/shorts_styles/<name>.json) 또는 JSON 경로 → 스타일 dict(기본값 병합)."""
    style = json.loads(json.dumps(PLAIN_STYLE))
    if not name_or_path or name_or_path == "plain":
        return style
    p = Path(name_or_path)
    if not p.exists():
        p = STYLE_DIR / f"{name_or_path}.json"
    if not p.exists():
        raise SystemExit(f"❌ 자막 스타일을 찾을 수 없습니다: {name_or_path} "
                         f"(data/shorts_styles/*.json 또는 JSON 경로)")
    data = json.loads(p.read_text(encoding="utf-8"))
    hook = dict(style["hook"])
    hook.update(data.pop("hook", {}) or {})
    style.update(data)
    style["hook"] = hook
    style.setdefault("name", p.stem)
    return style


def ass_color(hex_color: str, alpha: float = 0.0) -> str:
    """'#RRGGBB' → ASS '&HAABBGGRR' (alpha 0=불투명, 1=투명)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"색상은 #RRGGBB 형식이어야 합니다: {hex_color}")
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = max(0, min(255, int(round(alpha * 255))))
    return f"&H{a:02X}{b}{g}{r}".upper().replace("&H", "&H", 1)


_ALIGN = {"bottom": 2, "center": 5, "top": 8}


def installed_fonts() -> set[str]:
    """fc-list로 설치 폰트 패밀리 집합 (없으면 빈 집합)."""
    if shutil.which("fc-list") is None:
        return set()
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True,
                             text=True, timeout=20).stdout
    except Exception:
        return set()
    fams: set[str] = set()
    for line in out.splitlines():
        for fam in line.split(","):
            fams.add(fam.strip())
    return fams


def resolve_font(style: dict, fonts_dir: Path | None = None) -> str:
    """프리셋 폰트가 설치돼 있으면 그대로, 아니면 fallbacks 중 설치된 첫 폰트. 못 찾으면 프리셋 값."""
    preferred = style.get("font", "Pretendard")
    if fonts_dir and fonts_dir.exists():
        files = " ".join(p.name.lower() for p in fonts_dir.iterdir())
        if preferred.lower().replace(" ", "") in files.replace(" ", ""):
            return preferred
    fams = installed_fonts()
    if not fams:
        return preferred
    for cand in [preferred] + list(style.get("font_fallbacks") or []):
        if cand in fams:
            return cand
    return preferred


def _style_line(name: str, s: dict, font: str) -> str:
    border_style = 3 if s.get("box") else 1
    back = ass_color(s.get("box_color", "#000000"), 1 - float(s.get("box_alpha", 0.55))) \
        if s.get("box") else ass_color("#000000", 0.0)
    return ("Style: {name},{font},{size},{primary},{secondary},{outline_c},{back},"
            "{bold},0,0,0,100,100,{spacing},0,{border},{outline},{shadow},{align},"
            "{mh},{mh},{mv},1").format(
        name=name, font=font, size=int(s["size"]),
        primary=ass_color(s["color"]), secondary=ass_color(s.get("highlight_color", "#FFE100")),
        outline_c=ass_color(s.get("outline_color", "#000000")), back=back,
        bold=-1 if s.get("bold", True) else 0, spacing=s.get("spacing", 0),
        border=border_style, outline=s.get("outline", 4), shadow=s.get("shadow", 0),
        align=_ALIGN.get(s.get("align", "bottom"), 2),
        mh=int(s.get("margin_h", 60)), mv=int(s.get("margin_v", 360)))


def ass_header(style: dict, font: str) -> str:
    hook = dict(style)
    hook.update(style.get("hook") or {})
    hook.setdefault("bold", style.get("bold", True))
    return "\n".join([
        "[Script Info]",
        f"; 드림그로우 쇼츠 자막 — 스타일 프리셋 '{style.get('name', 'plain')}'",
        "ScriptType: v4.00+",
        f"PlayResX: {OUT_W}",
        f"PlayResY: {OUT_H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        _style_line("Caption", style, font),
        _style_line("Hook", hook, font),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]) + "\n"


def ass_timestamp(sec: float) -> str:
    cs = int(round(max(0.0, sec) * 100))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


_HL_RE = re.compile(r"==(.+?)==")


def ass_text(text: str, style: dict, highlight_words: list[str] | None = None) -> str:
    """'==단어==' 마크업(+자동 강조 단어)을 ASS 색상 오버라이드로 바꾼다. 줄바꿈은 '|' 또는 '\\n'."""
    hl = ass_color(style.get("highlight_color", "#FFE100"))
    base = ass_color(style["color"])
    t = text.replace("\r", "").strip()
    for w in highlight_words or []:
        w = w.strip()
        if w and w in t and f"=={w}==" not in t:
            t = t.replace(w, f"=={w}==")
    t = _HL_RE.sub(lambda m: "{\\1c" + hl + "}" + m.group(1) + "{\\1c" + base + "}", t)
    t = t.replace("\n", "\\N").replace("|", "\\N")
    return t


def wrap_lines(text: str, max_chars: int) -> list[str]:
    """어절(공백) 단위로 max_chars 이하 줄로 나눈다. 한 어절이 더 길면 그대로 둔다."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and len(_HL_RE.sub(r"\1", cand)) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def chunk_entries(entries: list[tuple[float, float, str]], *, max_chars: int = 16,
                  max_lines: int = 2) -> list[tuple[float, float, str]]:
    """긴 자막 한 줄을 쇼츠식 짧은 자막 여러 장으로 나눈다(글자 수 비례로 시간 배분).

    각 장은 최대 max_lines줄, 줄당 max_chars자. 줄바꿈은 '|'로 표시된다.
    """
    out: list[tuple[float, float, str]] = []
    for start, end, text in entries:
        text = text.strip()
        if not text:
            continue
        lines = wrap_lines(text, max_chars)
        cards = ["|".join(lines[i:i + max_lines]) for i in range(0, len(lines), max_lines)]
        total_chars = sum(len(c.replace("|", "")) for c in cards) or 1
        t = start
        dur = max(0.0, end - start)
        for i, card in enumerate(cards):
            share = len(card.replace("|", "")) / total_chars
            t_end = end if i == len(cards) - 1 else t + dur * share
            out.append((t, t_end, card))
            t = t_end
    return out


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    """SRT → (start, end, text). 사람이 손본 subtitles.srt를 다시 읽는 용도."""
    entries: list[tuple[float, float, str]] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", "").strip())
    ts = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        m = None
        for i, ln in enumerate(lines):
            m = ts.search(ln)
            if m:
                body = lines[i + 1:]
                break
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        entries.append((s, e, "|".join(body)))
    return entries


def build_ass(entries: list[tuple[float, float, str]], style: dict, *, font: str,
              hook: str | None = None, hook_seconds: float | None = None,
              duration: float | None = None,
              highlight_words: list[str] | None = None) -> str:
    """자막 항목 + (선택) 상단 후킹 문구 → ASS 문서 문자열."""
    lines = [ass_header(style, font)]
    if hook:
        h_end = hook_seconds if hook_seconds and hook_seconds > 0 else duration
        if not h_end:
            h_end = max((e for _, e, _ in entries), default=0.0)
        hook_style = dict(style)
        hook_style.update(style.get("hook") or {})
        lines.append(f"Dialogue: 1,{ass_timestamp(0)},{ass_timestamp(h_end)},Hook,,0,0,0,,"
                     f"{ass_text(hook, hook_style, highlight_words)}")
    for s, e, text in entries:
        if not text.strip():
            continue
        lines.append(f"Dialogue: 0,{ass_timestamp(s)},{ass_timestamp(e)},Caption,,0,0,0,,"
                     f"{ass_text(text, style, highlight_words)}")
    return "\n".join(lines) + "\n"


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
        body = text.strip().replace("|", "\n")
        lines.append(f"{i}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{body}\n")
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


# ------------------------------------------------------------------- 입력 찾기

def resolve_input(arg: str, source_dir: str | None = None) -> Path:
    """경로면 그대로, 확장자 없는 이름이면 source_dir(또는 DG_OSMO_DIR)에서 영상을 찾는다.

    DJI는 같은 이름의 .LRF(프록시)·.WAV(음성)를 함께 만들므로 VIDEO_EXTS만 본다.
    """
    p = Path(arg).expanduser()
    if p.exists():
        return p
    roots: list[Path] = []
    if source_dir:
        roots.append(Path(source_dir).expanduser())
    if os.getenv("DG_OSMO_DIR"):
        roots.append(Path(os.environ["DG_OSMO_DIR"]).expanduser())
    roots.append(Path.cwd())
    stem = p.stem if p.suffix.lower() in VIDEO_EXTS else p.name
    for root in roots:
        if not root.is_dir():
            continue
        hits = sorted(q for q in root.iterdir()
                      if q.suffix.lower() in VIDEO_EXTS and
                      (q.stem == stem or q.stem.lower() == stem.lower()))
        if not hits:
            hits = sorted(q for q in root.iterdir()
                          if q.suffix.lower() in VIDEO_EXTS and q.stem.lower().startswith(stem.lower()))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SystemExit("❌ 이름이 여러 영상과 겹칩니다: " + ", ".join(h.name for h in hits))
    searched = ", ".join(str(r) for r in roots if r.is_dir()) or "(폴더 없음)"
    raise SystemExit(f"❌ 영상을 찾지 못했습니다: {arg}  (찾은 곳: {searched})\n"
                     "   --source-dir <촬영본 폴더> 또는 환경변수 DG_OSMO_DIR을 지정하세요.")


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
                   "fit": args.fit, "style": args.style, "hook": args.hook},
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
    style = load_style(args.style)
    entries = chunk_entries(entries, max_chars=int(args.max_chars or style["max_chars"]),
                            max_lines=int(style.get("max_lines", 2)))
    srt = outdir / "subtitles.srt"
    srt.write_text(to_srt(entries), encoding="utf-8")
    log(f"  자막 {len(entries)}장 → {srt}  (문구 수정 후 --mode burn, 강조는 ==단어==)")
    return srt


def fonts_dir_for(args) -> Path | None:
    if getattr(args, "fonts_dir", None):
        return Path(args.fonts_dir).expanduser()
    if FONTS_DIR.is_dir() and any(FONTS_DIR.iterdir()):
        return FONTS_DIR
    return None


def burn(outdir: Path, args, plan: dict | None = None) -> Path:
    cut, srt = outdir / "cut.mp4", outdir / "subtitles.srt"
    if not srt.exists():
        raise SystemExit("❌ subtitles.srt 없음 — --mode subs를 먼저 실행하세요.")
    style = load_style(args.style)
    if args.sub_font:
        style["font"] = args.sub_font
    if args.sub_size:
        style["size"] = int(args.sub_size)
    fonts_dir = fonts_dir_for(args)
    font = resolve_font(style, fonts_dir)
    if font != style.get("font"):
        log(f"  ℹ️ 폰트 '{style.get('font')}' 미설치 → '{font}'로 대체 "
            "(data/fonts/에 otf를 넣거나 설치하면 원래 폰트 사용)")
    entries = parse_srt(srt.read_text(encoding="utf-8"))
    duration = (plan or {}).get("duration_out")
    if not duration:
        try:
            duration = probe(cut)["duration"]
        except Exception:
            duration = None
    hl = [w for w in (args.highlight or "").split(",") if w.strip()]
    ass = outdir / "subtitles.ass"
    ass.write_text(build_ass(entries, style, font=font, hook=args.hook,
                             hook_seconds=args.hook_seconds, duration=duration,
                             highlight_words=hl), encoding="utf-8")
    final = outdir / "final.mp4"
    subprocess.run(burn_cmd(cut, ass, final, fonts_dir=fonts_dir), check=True)
    log(f"🔥 자막 굽기 완료 (스타일 {style.get('name')}, 폰트 {font}): {final}")
    return final


def write_notes(outdir: Path, plan: dict, final: Path | None, args=None) -> None:
    claps = plan.get("claps") or []
    style = (plan.get("params") or {}).get("style") or getattr(args, "style", DEFAULT_STYLE)
    lines = [
        f"# 쇼츠 편집 노트 — {Path(plan['input']).name}", "",
        f"- 원본 {plan['duration_in']}초 → 편집 후 {plan['duration_out']}초",
        f"- 세그먼트 {len(plan['segments'])}개, 박수(NG) 컷 {len(claps)}건"
        + (f" ({', '.join(f'{t}s' for t in claps)})" if claps else ""),
        f"- 자막 스타일: {style} (data/shorts_styles/{style}.json)"
        + (f" / 후킹: {args.hook}" if args is not None and getattr(args, 'hook', None) else ""),
        f"- 결과물: {final.name if final else 'cut.mp4 (자막 없음)'} / subtitles.srt / "
        "subtitles.ass / edit_plan.json",
        "", "## 다듬기",
        "- 자막 문구 수정: subtitles.srt 고친 뒤 `--mode burn` 재실행 (재분석 불필요)",
        "- 강조(노란색): srt에서 `==단어==` 로 감싸기, 또는 `--highlight 단어,단어`",
        "- 상단 후킹 자막: `--hook \"첫 줄|둘째 줄\"` (`--hook-seconds 4`로 노출 시간 제한)",
        "- 스타일 자체 변경: data/shorts_styles/<이름>.json 수정 후 `--style <이름>` 으로 burn",
        "- 컷 수정: edit_plan.json의 segments 손본 뒤 `--mode render` → `concat` → `burn`",
        "", "## 마무리(캡컷) 재료",
        "- BGM·효과음·전환은 final.mp4 위에 캡컷에서 얹기",
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
    final = burn(outdir, args, plan) if srt else None
    write_notes(outdir, plan, final, args)
    log(f"✅ 완료: {final or (outdir / 'cut.mp4')}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="쇼츠 자동 편집 (무음/NG 컷 + 9:16 + 스타일 자막)")
    ap.add_argument("input", help="영상 파일·폴더, 또는 확장자 없는 영상 이름(--source-dir에서 찾음)")
    ap.add_argument("--source-dir", help="이름만 줬을 때 영상을 찾을 폴더 (기본: 환경변수 DG_OSMO_DIR)")
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
    ap.add_argument("--style", default=DEFAULT_STYLE,
                    help="자막 스타일 프리셋 이름(data/shorts_styles) 또는 JSON 경로. plain=기본")
    ap.add_argument("--hook", help="상단 후킹 자막 문구 ('|'로 줄바꿈, ==단어==로 강조)")
    ap.add_argument("--hook-seconds", type=float, default=0.0,
                    help="후킹 자막 노출 시간(초). 0이면 영상 내내")
    ap.add_argument("--highlight", help="자동 강조할 단어들 (쉼표 구분)")
    ap.add_argument("--max-chars", type=int, help="자막 한 줄 최대 글자 수 (기본: 프리셋 값)")
    ap.add_argument("--fonts-dir", help="설치 없이 쓸 폰트 폴더 (기본: data/fonts/ 있으면 사용)")
    ap.add_argument("--sub-font", help="프리셋 폰트 덮어쓰기")
    ap.add_argument("--sub-size", type=int, help="프리셋 자막 크기 덮어쓰기 (1080x1920 기준 px)")
    return ap


def main(argv: list[str] | None = None) -> None:
    if sys.platform == "win32":  # 콘솔 cp949 깨짐 방지
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    require_ffmpeg()
    load_style(args.style)  # 프리셋 오류는 렌더 전에 바로 알린다
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
    target = resolve_input(args.input, args.source_dir)

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
        plan = load_plan(outdir)
        burn(outdir, args, plan)
        write_notes(outdir, plan, outdir / "final.mp4", args)


if __name__ == "__main__":
    main()
