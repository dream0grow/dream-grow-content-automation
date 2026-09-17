"""shorts_edit 테스트 — ffmpeg/Whisper 없이 컷 로직·명령 빌더를 검증한다."""
import math
import struct
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import shorts_edit as se

WIN = se.WIN_SEC  # 0.05초


def env(seconds_db: list[tuple[float, float]]) -> list[float]:
    """[(길이초, dB), ...] 를 창 단위 엔벨로프로 펼친다."""
    out: list[float] = []
    for sec, db in seconds_db:
        out.extend([db] * int(round(sec / WIN)))
    return out


class TestEnvelope(unittest.TestCase):
    def test_rms_envelope_silence_and_tone(self):
        sr = se.SAMPLE_RATE
        silence = b"\x00\x00" * sr  # 1초 무음
        tone = struct.pack(f"<{sr}h", *([16384] * sr))  # 1초 -6dBFS 직류
        db = se.rms_envelope(silence + tone)
        self.assertEqual(len(db), int(2 / WIN))
        self.assertLessEqual(db[0], se.DB_FLOOR)
        self.assertAlmostEqual(db[-1], 20 * math.log10(0.5), places=1)


class TestSpeechSegments(unittest.TestCase):
    def test_long_silence_cut_with_pad(self):
        e = env([(2.0, -20), (3.0, -60), (2.0, -20)])
        segs = se.speech_segments(e, min_silence=0.9, pad=0.3)
        self.assertEqual(len(segs), 2)
        self.assertAlmostEqual(segs[0][0], 0.0, places=2)
        self.assertAlmostEqual(segs[0][1], 2.3, places=2)  # 뒤 0.3초 여유
        self.assertAlmostEqual(segs[1][0], 4.7, places=2)  # 앞 0.3초 여유

    def test_short_silence_kept(self):
        e = env([(2.0, -20), (0.5, -60), (2.0, -20)])
        segs = se.speech_segments(e, min_silence=0.9, pad=0.3)
        self.assertEqual(len(segs), 1)  # 0.5초 호흡은 병합

    def test_tiny_blip_dropped(self):
        e = env([(0.1, -20), (5.0, -60)])
        segs = se.speech_segments(e, min_silence=0.9, pad=0.3, min_speech=0.3)
        self.assertEqual(segs, [])

    def test_pad_overlap_merges(self):
        e = env([(1.0, -20), (1.0, -60), (1.0, -20)])
        segs = se.speech_segments(e, min_silence=0.9, pad=0.6)
        self.assertEqual(len(segs), 1)  # 여유가 겹치면 하나로

    def test_empty(self):
        self.assertEqual(se.speech_segments([]), [])


class TestClaps(unittest.TestCase):
    def test_detects_short_loud_spike(self):
        e = env([(2.0, -25), (0.15, -2), (2.0, -25)])
        claps = se.detect_claps(e)
        self.assertEqual(len(claps), 1)
        self.assertAlmostEqual(claps[0], 2.0, places=1)

    def test_long_loud_not_clap(self):
        e = env([(1.0, -25), (1.0, -2), (1.0, -25)])
        self.assertEqual(se.detect_claps(e), [])

    def test_min_gap_dedup(self):
        e = env([(1.0, -25), (0.1, -2), (0.2, -25), (0.1, -2), (1.0, -25)])
        self.assertEqual(len(se.detect_claps(e, min_gap=0.8)), 1)


class TestApplyClaps(unittest.TestCase):
    def test_clap_inside_segment_cuts_take_before(self):
        segs = [[0.0, 10.0]]
        out = se.apply_claps(segs, [4.0], cut_after=0.2)
        self.assertEqual(out, [[4.2, 10.0]])

    def test_clap_in_silence_drops_previous_segment(self):
        segs = [[0.0, 3.0], [6.0, 10.0]]
        out = se.apply_claps(segs, [4.0])
        self.assertEqual(out, [[6.0, 10.0]])

    def test_clap_near_segment_end_drops_it(self):
        segs = [[0.0, 3.0], [5.0, 8.0]]
        out = se.apply_claps(segs, [2.95], cut_after=0.2, min_speech=0.3)
        self.assertEqual(out, [[5.0, 8.0]])

    def test_clap_before_everything_is_noop(self):
        segs = [[2.0, 5.0]]
        self.assertEqual(se.apply_claps(segs, [0.5]), [[2.0, 5.0]])


class TestVerticalFilter(unittest.TestCase):
    def test_landscape_crops_sides(self):
        vf = se.vertical_filter(3840, 2160)
        self.assertIn("crop=ih*9/16:ih", vf)
        self.assertIn("scale=1080:1920", vf)

    def test_vertical_source_crops_topbottom_only_if_taller(self):
        vf = se.vertical_filter(1080, 2160)  # 1:2 — 9:16보다 세로로 김
        self.assertIn("crop=iw:iw*16/9", vf)

    def test_blur_fit(self):
        vf = se.vertical_filter(3840, 2160, fit="blur")
        self.assertIn("boxblur", vf)
        self.assertIn("overlay", vf)


class TestCommands(unittest.TestCase):
    def test_segment_cmd(self):
        cmd = se.segment_cmd(Path("in.mp4"), [1.5, 4.0], Path("seg.mp4"), "vfx")
        self.assertIn("-ss", cmd)
        self.assertEqual(cmd[cmd.index("-ss") + 1], "1.500")
        self.assertEqual(cmd[cmd.index("-to") + 1], "4.000")
        self.assertIn("libx264", cmd)

    def test_burn_cmd_uses_ass_and_fontsdir(self):
        cmd = se.burn_cmd(Path("cut.mp4"), Path("s.ass"), Path("f.mp4"),
                          fonts_dir=Path("/repo/data/fonts"))
        vf = cmd[cmd.index("-vf") + 1]
        self.assertTrue(vf.startswith("ass='"))
        self.assertIn("fontsdir=", vf)
        self.assertNotIn("fontsdir", se.burn_cmd(Path("c.mp4"), Path("s.ass"), Path("f.mp4"))[
            se.burn_cmd(Path("c.mp4"), Path("s.ass"), Path("f.mp4")).index("-vf") + 1])

    def test_sub_filter_path_windows(self):
        self.assertEqual(se.sub_filter_path(Path("C:\\a\\b.srt")).count("\\:"), 1)


class TestSrt(unittest.TestCase):
    def test_timestamp(self):
        self.assertEqual(se.srt_timestamp(3661.5), "01:01:01,500")

    def test_to_srt(self):
        srt = se.to_srt([(0.0, 1.2, " 안녕하세요 "), (1.2, 2.0, "쇼츠입니다")])
        self.assertIn("1\n00:00:00,000 --> 00:00:01,200\n안녕하세요\n", srt)
        self.assertIn("2\n", srt)




class TestProbeFallback(unittest.TestCase):
    def test_parse_ffmpeg_info(self):
        stderr = ("Input #0, mov,mp4, from 'x.mp4':\n  Duration: 00:01:02.50, start: 0.000000\n"
                  "  Stream #0:0: Video: hevc (Main), yuv420p, 3840x2160, 24 fps, 24 tbr\n")
        info = se.parse_ffmpeg_info(stderr)
        self.assertEqual((info["width"], info["height"]), (3840, 2160))
        self.assertAlmostEqual(info["duration"], 62.5)
        self.assertEqual(info["fps"], 24.0)


class TestStyle(unittest.TestCase):
    def test_ass_color(self):
        self.assertEqual(se.ass_color("#FFE600"), "&H0000E6FF")
        self.assertEqual(se.ass_color("#000000", alpha=0.5), "&H80000000")

    def test_load_growcircle_preset_merges_defaults(self):
        st = se.load_style("growcircle")
        self.assertEqual(st["name"], "growcircle")
        self.assertIn("hook", st)
        self.assertEqual(st["hook"]["align"], "top")
        self.assertTrue(st["max_chars"] >= 8)

    def test_load_plain(self):
        self.assertEqual(se.load_style(None)["name"], "plain")

    def test_unknown_style_exits(self):
        with self.assertRaises(SystemExit):
            se.load_style("없는프리셋")

    def test_ass_text_highlight_markup(self):
        st = se.load_style("plain")
        t = se.ass_text("아이의 ==마음==을 보세요", st)
        self.assertIn("{\\1c" + se.ass_color(st["highlight_color"]) + "}마음", t)
        self.assertIn("{\\1c" + se.ass_color(st["color"]) + "}을 보세요", t)

    def test_ass_text_auto_highlight_and_linebreak(self):
        st = se.load_style("plain")
        t = se.ass_text("첫 줄|둘째 줄 마음", st, highlight_words=["마음"])
        self.assertIn("\\N", t)
        self.assertIn("}마음{", t)

    def test_build_ass_has_styles_and_hook(self):
        st = se.load_style("growcircle")
        doc = se.build_ass([(0.0, 1.5, "안녕하세요"), (1.5, 3.0, "==쇼츠==입니다")], st,
                           font="Pretendard", hook="선생님이|알려주는 방법", hook_seconds=0,
                           duration=3.0)
        self.assertIn("PlayResX: 1080", doc)
        self.assertIn("Style: Caption,Pretendard,", doc)
        self.assertIn("Style: Hook,Pretendard,", doc)
        self.assertIn("Dialogue: 1,0:00:00.00,0:00:03.00,Hook", doc)
        self.assertIn("선생님이\\N알려주는 방법", doc)
        self.assertEqual(doc.count("Dialogue: 0,"), 2)

    def test_ass_timestamp(self):
        self.assertEqual(se.ass_timestamp(61.234), "0:01:01.23")


class TestChunking(unittest.TestCase):
    def test_wrap_lines(self):
        self.assertEqual(se.wrap_lines("아이가 학교 가기 싫다고 할 때", 10),
                         ["아이가 학교 가기", "싫다고 할 때"])

    def test_wrap_ignores_highlight_markup_length(self):
        lines = se.wrap_lines("==아이가== 학교", 7)
        self.assertEqual(lines, ["==아이가== 학교"])

    def test_chunk_splits_long_entry_proportionally(self):
        entries = [(0.0, 4.0, "아이가 학교 가기 싫다고 할 때 부모가 먼저 해야 할 한 가지")]
        out = se.chunk_entries(entries, max_chars=8, max_lines=1)
        self.assertGreater(len(out), 2)
        self.assertAlmostEqual(out[0][0], 0.0)
        self.assertAlmostEqual(out[-1][1], 4.0)
        for (s, e, t) in out:
            self.assertLess(s, e)
            self.assertLessEqual(len(t), 8)

    def test_chunk_two_lines_per_card(self):
        out = se.chunk_entries([(0.0, 2.0, "하나 둘 셋 넷 다섯 여섯")], max_chars=5, max_lines=2)
        self.assertEqual(out[0][2].count("|"), 1)

    def test_parse_srt_roundtrip(self):
        srt = se.to_srt([(0.0, 1.2, "첫 줄|둘째 줄"), (1.2, 2.0, "==강조==")])
        back = se.parse_srt(srt)
        self.assertEqual(back[0][2], "첫 줄|둘째 줄")
        self.assertAlmostEqual(back[1][0], 1.2)
        self.assertEqual(back[1][2], "==강조==")


class TestResolveInput(unittest.TestCase):
    def test_name_resolves_mp4_and_skips_lrf(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for name in ("DJI_0008_D.MP4", "DJI_0008_D.LRF", "DJI_0008_D.WAV", "DJI_0009_D.MP4"):
                (Path(d) / name).write_bytes(b"")
            self.assertEqual(se.resolve_input("DJI_0008_D", d).name, "DJI_0008_D.MP4")
            self.assertEqual(se.resolve_input("DJI_0008_D.MP4", d).name, "DJI_0008_D.MP4")
            with self.assertRaises(SystemExit):
                se.resolve_input("DJI_000", d)  # 여러 개와 겹침

    def test_missing_name_exits(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                se.resolve_input("없는영상", d)


if __name__ == "__main__":
    unittest.main()
