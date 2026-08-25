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

    def test_burn_cmd_styles(self):
        cmd = se.burn_cmd(Path("cut.mp4"), Path("s.srt"), Path("f.mp4"),
                          font="Pretendard", size=15)
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("FontName=Pretendard", vf)
        self.assertIn("Alignment=2", vf)

    def test_sub_filter_path_windows(self):
        self.assertEqual(se.sub_filter_path(Path("C:\\a\\b.srt")).count("\\:"), 1)


class TestSrt(unittest.TestCase):
    def test_timestamp(self):
        self.assertEqual(se.srt_timestamp(3661.5), "01:01:01,500")

    def test_to_srt(self):
        srt = se.to_srt([(0.0, 1.2, " 안녕하세요 "), (1.2, 2.0, "쇼츠입니다")])
        self.assertIn("1\n00:00:00,000 --> 00:00:01,200\n안녕하세요\n", srt)
        self.assertIn("2\n", srt)


if __name__ == "__main__":
    unittest.main()
