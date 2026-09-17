"""Boundary checks for edits that would otherwise lose speech or desynchronize captions."""
import copy
import unittest
from shorts.render import clip_gap_seconds, resolve_playback_rate, timecode, validate


class EditValidationTests(unittest.TestCase):
    def setUp(self):
        self.job = {"clips":[{"start":1,"end":3,"captions":[
            {"start":1,"end":2,"text":"첫 문장"},
            {"start":2,"end":3,"text":"둘째 문장"}]}]}

    def test_touching_cues_and_frame_duration(self):
        self.assertEqual(validate(self.job,10,30),60)
        self.assertEqual(timecode(30*61+15,30),"00:01:01,500")

    def test_overlapping_cues_fail(self):
        job=copy.deepcopy(self.job)
        job["clips"][0]["captions"][1]["start"]=1.9
        with self.assertRaises(ValueError): validate(job,10,30)

    def test_caption_outside_cut_fails(self):
        job=copy.deepcopy(self.job)
        job["clips"][0]["captions"][1]["end"]=3.1
        with self.assertRaises(ValueError): validate(job,10,30)

    def test_source_end_and_duration_limit(self):
        with self.assertRaises(ValueError): validate(self.job,2.9,30)
        self.job["max_duration"]=1
        with self.assertRaises(ValueError): validate(self.job,10,30)

    def test_cut_gap_extends_only_between_clips(self):
        job={"clips":[
            {"start":1,"end":3,"captions":[{"start":1,"end":2,"text":"가"}]},
            {"start":4,"end":6,"captions":[{"start":4,"end":5,"text":"나"}]}]}
        # 2s + 2s = 4s baseline; a 0.3s gap adds 9 frames between the two cuts (not after the last).
        self.assertEqual(validate(job,10,30,0.3),129)
        # Per-clip override wins.
        job["clips"][0]["gap_after"]=0.5
        self.assertEqual(validate(job,10,30,0.3),135)
        # Without an explicit gap_after, the final clip has no trailing hold.
        self.assertEqual(clip_gap_seconds(job["clips"],1,0.3),0.0)

    def test_trailing_gap_on_last_clip(self):
        job={"clips":[
            {"start":1,"end":3,"captions":[{"start":1,"end":2,"text":"가"}]},
            {"start":4,"end":6,"gap_after":0.5,"captions":[{"start":4,"end":5,"text":"나"}]}]}
        # 4s baseline + 0.5s tail hold on the last clip = 4.5s = 135 frames. No between-clip gap.
        self.assertEqual(validate(job,10,30,0),135)
        self.assertEqual(clip_gap_seconds(job["clips"],1,0),0.5)

    def test_caption_may_extend_into_trailing_hold(self):
        # A silent text end card: the last clip holds 3s and captions run over the frozen frame.
        job={"clips":[
            {"start":1,"end":3,"captions":[{"start":1,"end":2,"text":"가"}]},
            {"start":4,"end":6,"gap_after":3.0,"captions":[
                {"start":4,"end":5,"text":"나"},
                {"start":6,"end":9,"text":"댓글 남겨주세요"}]}]}
        self.assertEqual(validate(job,10,30,0.3),(2+2+3)*30+9)
        # ...but not beyond the hold.
        job["clips"][1]["captions"][1]["end"]=9.1
        with self.assertRaises(ValueError): validate(job,10,30,0.3)
        # Between clips the cut_gap hold is also usable.
        job["clips"][1]["captions"][1]["end"]=9
        job["clips"][0]["captions"].append({"start":3,"end":3.3,"text":"가-hold"})
        self.assertEqual(validate(job,10,30,0.3),(2+2+3)*30+9)

    def test_gap_after_must_be_non_negative(self):
        job={"clips":[
            {"start":1,"end":3,"gap_after":-0.1,"captions":[{"start":1,"end":2,"text":"가"}]},
            {"start":4,"end":6,"captions":[{"start":4,"end":5,"text":"나"}]}]}
        with self.assertRaises(ValueError): validate(job,10,30,0)


    def test_playback_rate_default_and_precedence(self):
        # Style default only.
        self.assertEqual(resolve_playback_rate({}, {"playback_rate": 1.2}), 1.2)
        # Job overrides style.
        self.assertEqual(resolve_playback_rate({"playback_rate": 1.0}, {"playback_rate": 1.2}), 1.0)
        # No config → 1.0.
        self.assertEqual(resolve_playback_rate({}, {}), 1.0)

    def test_playback_rate_bounds(self):
        # atempo's usable single-stage range.
        with self.assertRaises(ValueError): resolve_playback_rate({"playback_rate": 0.4}, {})
        with self.assertRaises(ValueError): resolve_playback_rate({"playback_rate": 2.1}, {})


if __name__=="__main__": unittest.main()
