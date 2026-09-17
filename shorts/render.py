"""Reproducible local video + caption renderer. Run python3 -m shorts.render --help."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import unicodedata

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def run(args, log=None):
    if args[0] == "ffmpeg" and "-xerror" not in args:
        args = [args[0], "-xerror", *args[1:]]
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if log:
        Path(log).write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return result.stdout


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def resolve_source(job):
    if job.get("source"):
        path = Path(job["source"]).expanduser().resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(path)
    base = Path(job["source_root"]).expanduser()
    name = unicodedata.normalize("NFC", job["source_name"])
    matches = [p for p in base.glob("*/*/*") if unicodedata.normalize("NFC", p.name) == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one source, found {len(matches)}: {matches}")
    return matches[0].resolve()


def prepare(source, dest, model):
    """Extract synchronized speech and retain raw word timestamps for editorial review."""
    import mlx_whisper
    dest.mkdir(parents=True, exist_ok=True)
    metadata = probe(source)
    write_json(dest / "source.json", {"path": str(source), "size": source.stat().st_size, "probe": metadata})
    wav = dest / "speech.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", source, "-map", "0:a:0", "-ac", "1", "-ar", "16000", wav])
    transcript = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language="ko",
        word_timestamps=True, condition_on_previous_text=False, verbose=False,
        initial_prompt="드림그로우, 그로우써클, 학부모, 교육")
    write_json(dest / "transcript.json", transcript)
    (dest / "transcript.txt").write_text("\n".join(
        f"{s['start']:.2f}–{s['end']:.2f} {s['text'].strip()}"
        for s in transcript["segments"] if s["end"] > s["start"]))
    print(dest / "transcript.txt", flush=True)


def resolve_playback_rate(job, style):
    """Time-stretch factor applied at final composition: job wins over style, defaults to 1.0.

    Constrained to [0.5, 2.0] because ffmpeg's atempo does one stage without cascading.
    """
    rate = float(job.get("playback_rate", style.get("playback_rate", 1.0)))
    if not 0.5 <= rate <= 2.0:
        raise ValueError("playback_rate must be in [0.5, 2.0] (atempo limit); split into stages if needed")
    return rate


def clip_gap_seconds(clips, index, cut_gap):
    """Trailing hold length after a cut.

    Between clips: cut_gap by default, overridable per clip via gap_after.
    After the last clip: 0 by default, but a per-clip gap_after still works as a tail hold
    (used to leave breathing room before the video ends).
    """
    is_last = index >= len(clips) - 1
    default = 0.0 if is_last else cut_gap
    gap = clips[index].get("gap_after", default)
    if gap < 0:
        raise ValueError("gap_after must be non-negative")
    return float(gap)


def validate(job, source_duration, fps, cut_gap=0.0):
    if not job.get("clips"):
        raise ValueError("No clips")
    clips = job["clips"]
    for i, clip in enumerate(clips):
        start, end = clip["start"], clip["end"]
        if not 0 <= start < end <= source_duration:
            raise ValueError(f"Invalid clip interval: {start}, {end}")
        # Captions may extend into the trailing hold (frozen last frame) of the clip.
        # This is how a silent text end card (e.g. a lead-magnet CTA) is expressed.
        limit = end + clip_gap_seconds(clips, i, cut_gap)
        previous = start
        for cue in clip.get("captions", []):
            if not start <= cue["start"] < cue["end"] <= limit + 1e-6 or cue["start"] < previous:
                raise ValueError(f"Overlapping/out-of-range caption: {cue}")
            if not cue["text"].strip():
                raise ValueError("Empty caption")
            previous = cue["end"]
        if not 0 <= clip.get("center_x", .5) <= 1:
            raise ValueError("center_x must be in [0, 1]")
        if clip.get("zoom", 1) < 1:
            raise ValueError("zoom must be >= 1")
    total_frames = 0
    for i, c in enumerate(clips):
        total_frames += round((c["end"] - c["start"]) * fps)
        total_frames += round(clip_gap_seconds(clips, i, cut_gap) * fps)
    if total_frames / fps > job.get("max_duration", 60):
        raise ValueError("Edit exceeds the job's maximum duration")
    return total_frames


def font(path, size):
    return ImageFont.truetype(str(Path(path).expanduser()), size)


def text_layer(text, face, color, max_width, skew=0, shadow_radius=0, stroke=0):
    f = face
    bbox = f.getbbox(text, stroke_width=stroke)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 30
    layer = Image.new("RGBA", (math.ceil(w + h * abs(skew)) + pad * 2, h + pad * 2))
    ImageDraw.Draw(layer).text((pad - bbox[0], pad - bbox[1]), text, font=f,
        fill=color, stroke_width=stroke, stroke_fill="#111111")
    if skew:
        # Right-leaning italic: shift top of glyphs to the right.
        layer = layer.transform(layer.size, Image.Transform.AFFINE,
            (1, skew, -skew * layer.height, 0, 1, 0), Image.Resampling.BICUBIC)
    if layer.width > max_width + pad * 2:
        raise ValueError(f"Text too wide ({layer.width - pad*2}px): {text!r}; split the cue or reduce font size")
    if shadow_radius:
        alpha = layer.getchannel("A")
        shadow = Image.new("RGBA", layer.size, "black")
        shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(shadow_radius)))
        shadow.alpha_composite(layer)
        layer = shadow
    return layer


def centered(canvas, layer, x, y):
    canvas.alpha_composite(layer, (round(x - layer.width / 2), round(y - layer.height / 2)))


def graphics(job, style, work, fps):
    w, h = style["width"], style["height"]
    layout = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    box = style["video_box"]
    ImageDraw.Draw(layout).rectangle((0, box["y"], w-1, box["y"]+box["height"]-1), fill=(0,0,0,0))
    for line, spec in zip(job["title_lines"], style["title_lines"]):
        centered(layout, text_layer(line, font(style["title_font"], spec["size"]), spec["color"], w-120), w/2, spec["y"])
    centered(layout, text_layer(job.get("brand", "드림그로우"), font(style["caption_font"], 32), "#777777", w-120), w/2, style["brand_y"])
    layout.save(work / "layout.png")
    height = style["caption_strip_height"]
    transparent = Image.new("RGBA", (w, height))
    transparent.save(work / "caption_blank.png")
    events = []
    offset = 0
    cut_gap = style.get("cut_gap", 0.0)
    clips = job["clips"]
    for i, clip in enumerate(clips):
        count = round((clip["end"] - clip["start"]) * fps)
        gap_frames = round(clip_gap_seconds(clips, i, cut_gap) * fps)
        for cue in clip.get("captions", []):
            start = offset + round((cue["start"] - clip["start"]) * fps)
            # A cue may run into the clip's trailing hold (end card over the frozen frame).
            end = min(offset + count + gap_frames, offset + round((cue["end"] - clip["start"]) * fps))
            if end <= start:
                raise ValueError(f"Caption shorter than one frame: {cue}")
            events.append({"start_frame": start, "end_frame": end, "text": cue["text"]})
        offset += count + gap_frames
    concat = []
    def entry(filename, frames):
        if frames:
            concat.extend([f"file '{filename}'", f"option framerate {fps}", f"duration {frames/fps:.9f}"])
    previous = 0
    for i, cue in enumerate(events):
        entry("caption_blank.png", cue["start_frame"] - previous)
        canvas = transparent.copy()
        lines = cue["text"].split("\n")
        if len(lines)>2:
            raise ValueError("At most two caption lines")
        for j, line in enumerate(lines):
            layer = text_layer(line, font(style["caption_font"], style["caption_size"]), style["caption_color"],
                w-140, style["caption_skew"], style["caption_shadow"], style["caption_stroke"])
            centered(canvas, layer, w/2, height/2+(j-(len(lines)-1)/2)*style["caption_line_height"])
        name = f"caption_{i:03d}.png"
        canvas.save(work / name)
        entry(name, cue["end_frame"]-cue["start_frame"])
        previous = cue["end_frame"]
    entry("caption_blank.png", offset-previous)
    concat.extend(["file 'caption_blank.png'", f"option framerate {fps}"])
    (work / "captions.ffconcat").write_text("ffconcat version 1.0\n"+"\n".join(concat)+"\n")
    packets = json.loads(run(["ffprobe","-v","error","-f","concat","-safe","0",
        "-i",work/"captions.ffconcat","-show_packets","-show_entries","packet=pts_time","-of","json"]))["packets"]
    times = [float(p["pts_time"]) for p in packets]
    if any(b <= a for a,b in zip(times,times[1:])) or abs(times[-1]-offset/fps) > .001:
        raise ValueError("Caption stream timestamps do not match the edit; check image frame rates")
    write_json(work / "caption_timeline.json", events)
    return events


def timecode(frame, fps):
    ms = round(frame / fps * 1000)
    sec, milli = divmod(ms, 1000)
    minute, second = divmod(sec, 60)
    hour, minute = divmod(minute, 60)
    return f"{hour:02}:{minute:02}:{second:02},{milli:03}"


def render(job_path, output):
    job = json.loads(job_path.read_text())
    style_path = (ROOT / job["style"]).resolve()
    style = json.loads(style_path.read_text())
    source = resolve_source(job)
    metadata = probe(source)
    fps = style["fps"]
    cut_gap = style.get("cut_gap", 0.0)
    rate = resolve_playback_rate(job, style)
    frames = validate(job, float(metadata["format"]["duration"]), fps, cut_gap)
    output.mkdir(parents=True, exist_ok=True)
    work = output / "work"
    work.mkdir(exist_ok=True)
    write_json(output / "edit.json", job)
    write_json(output / "style.json", style)
    events = graphics(job, style, work, fps)
    (output / "captions.srt").write_text("\n\n".join(
        f"{i+1}\n{timecode(e['start_frame'],fps)} --> {timecode(e['end_frame'],fps)}\n{e['text']}"
        for i,e in enumerate(events))+"\n")
    w, h = style["width"], style["height"]
    box = style["video_box"]
    clips = job["clips"]
    for i, clip in enumerate(clips):
        n = round((clip["end"]-clip["start"])*fps)
        gap_seconds = clip_gap_seconds(clips, i, cut_gap)
        gap_frames = round(gap_seconds * fps)
        total = n + gap_frames
        cache_path = work / f"cut_{i:03d}.cache.json"
        cache_key = {"source":str(source), "size":source.stat().st_size, "mtime_ns":source.stat().st_mtime_ns,
            "clip":{k:v for k,v in clip.items() if k != "captions"},
            "gap_frames": gap_frames,
            "video_style":{k:style[k] for k in ("width","height","fps","video_box","brightness","saturation")}}
        if cache_path.exists() and (work/f"cut_{i:03d}.mkv").exists() and json.loads(cache_path.read_text()) == cache_key:
            print(f"Reusing cut {i+1}/{len(clips)}", flush=True)
            continue
        print(f"Rendering cut {i+1}/{len(clips)}: {clip['start']}–{clip['end']} (+{gap_seconds:.2f}s gap)", flush=True)
        # ffmpeg autorotates the DJI source using its display matrix before crop/scale.
        zoom = clip.get("zoom", 1)
        center = clip.get("center_x", .5)
        crop = f"crop=w='min(iw,ih*{w}/{box['height']})/{zoom}':h='min(ih,iw*{box['height']}/{w})/{zoom}':x='max(0,min(iw-ow,iw*{center}-ow/2))':y='(ih-oh)/2'"
        vf = f"{crop},scale={w}:{box['height']},setsar=1,fps={fps},eq=brightness={style['brightness']}:saturation={style['saturation']},pad={w}:{h}:0:{box['y']}:black"
        af = "aresample=48000,asetpts=PTS-STARTPTS"
        if gap_frames > 0:
            vf += f",tpad=stop_mode=clone:stop_duration={gap_frames/fps:.6f}"
            af += f",apad=pad_dur={gap_frames/fps:.6f}"
        run(["ffmpeg","-hide_banner","-y","-ss",clip["start"],"-i",source,"-t",total/fps,
            "-map","0:v:0","-map","0:a:0","-vf",vf,"-af",af,
            "-c:v","libx264","-preset","veryfast","-crf","16","-pix_fmt","yuv420p",
            "-c:a","pcm_s16le","-ar","48000","-ac","2","-map_metadata","-1",
            work/f"cut_{i:03d}.mkv"], work/f"cut_{i:03d}.log")
        write_json(cache_path, cache_key)
    (work/"cuts.ffconcat").write_text("ffconcat version 1.0\n"+"\n".join(
        f"file 'cut_{i:03d}.mkv'" for i in range(len(clips)))+"\n")
    # Two-pass EBU R128 audio normalization, with original synchronized source audio.
    measure = subprocess.run(["ffmpeg","-xerror","-hide_banner","-f","concat","-safe","0","-i",str(work/"cuts.ffconcat"),
        "-af","aformat=sample_fmts=dblp,highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json","-vn","-f","null","-"],capture_output=True,text=True)
    if measure.returncode:
        raise RuntimeError(measure.stderr[-3000:])
    stats, _ = json.JSONDecoder().raw_decode(measure.stderr[measure.stderr.rfind("{"):])
    write_json(output/"loudness_input.json",stats)
    norm = f"aformat=sample_fmts=dblp,highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true,afade=t=in:d=0.025,afade=t=out:st={frames/fps-.08}:d=0.08"
    if rate != 1.0:
        # Time-stretch after loudness normalization so the fade positions stay stable pre-stretch.
        norm += f",atempo={rate:.6f}"
    video_tail = "" if rate == 1.0 else f",setpts=PTS/{rate:.6f}"
    final_duration = frames / fps / rate
    print(f"Compositing title, captions and normalized audio (playback_rate={rate})", flush=True)
    target = output/job["output_name"]
    temp = target.with_suffix(".rendering.mp4")
    run(["ffmpeg","-hide_banner","-y","-f","concat","-safe","0","-i",work/"cuts.ffconcat",
        "-loop","1","-framerate",fps,"-i",work/"layout.png",
        "-f","concat","-safe","0","-i",work/"captions.ffconcat",
        "-filter_complex",f"[0:v][1:v]overlay=0:0[layout];[layout][2:v]overlay=0:{style['caption_y']}:eof_action=pass{video_tail}[v]",
        "-map","[v]","-map","0:a:0","-t",final_duration,"-r",fps,
        "-af",norm,"-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","192k","-ar","48000","-movflags","+faststart","-map_metadata","-1",temp],work/"final.log")
    actual = probe(temp)
    video = next(s for s in actual["streams"] if s["codec_type"]=="video")
    if (video["width"],video["height"]) != (w,h) or abs(float(actual["format"]["duration"])-final_duration)>.12:
        raise RuntimeError("Output dimensions/duration verification failed")
    # Decode all frames; abort instead of presenting a partially encoded video.
    run(["ffmpeg","-v","error","-i",temp,"-f","null","-"],work/"decode_check.log")
    temp.replace(target)
    digest = hashlib.sha256(job_path.read_bytes()+style_path.read_bytes()).hexdigest()
    write_json(output/"manifest.json",{"status":"rendered", "editorial_review":"agent-reviewed sample",
        "source":str(source),"source_size":source.stat().st_size,"source_mtime_ns":source.stat().st_mtime_ns,
        "job_style_sha256":digest,"output":str(target.resolve()),
        "edit_duration":frames/fps,"playback_rate":rate,"duration":final_duration,
        "dimensions":[w,h],"fps":fps,"caption_count":len(events),"reference":job["reference"],
        "font_match":"visual approximation, original font unverified", "probe":actual})
    print(target.resolve(),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    prep=sub.add_parser("prepare",help="Extract speech and Korean word timestamps locally (Apple Silicon)")
    prep.add_argument("--source",type=Path,required=True)
    prep.add_argument("--output",type=Path,required=True)
    prep.add_argument("--model",default="mlx-community/whisper-large-v3-mlx")
    ren=sub.add_parser("render",help="Render a reviewed edit JSON into MP4 + SRT + manifest")
    ren.add_argument("--job",type=Path,required=True)
    ren.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    for binary in ("ffmpeg","ffprobe"):
        if not shutil.which(binary):
            parser.error(f"Missing dependency: {binary}")
    if args.command=="prepare":
        prepare(args.source.expanduser().resolve(),args.output.resolve(),args.model)
    else:
        render(args.job.resolve(),args.output.resolve())


if __name__=="__main__":
    main()
