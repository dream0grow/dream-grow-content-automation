"""reels_video 테스트 — 네트워크 없이 파싱/프롬프트/폴링/합본 명령을 검증한다."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import reels_video as rv

SAMPLE_MD = """---
주제: 좋은 훈육
채널: reels
---

**[0~3초] 후킹**
"아이가 말을 잘 듣는다고요?"
*(화면: 부모가 시키자마자 행동하는 아이 클로즈업)*

## 3. B-roll 장면 목록

| 타임코드 | 장면 | Pexels/Pixabay 키워드 (영어) | 대체 옵션 |
|---------|------|----------------------------|----------|
| 0~3초 | 무표정한 아이 클로즈업 | `child obedient parent`, `kid blank face` | 옆모습 |
| 3~10초 | 교실에서 정리하는 아이 | `classroom kids cleaning` | 손 클로즈업 |
| 38~45초 | 리드마그넷 PDF 모션 그래픽 | (자체 제작) | 템플릿 |
"""


class TestParsing(unittest.TestCase):
    def test_broll_table(self):
        scenes = rv.parse_broll_table(SAMPLE_MD)
        self.assertEqual(len(scenes), 2)  # (자체 제작) 행 제외
        self.assertEqual(scenes[0]["timecode"], "0~3초")
        self.assertEqual(scenes[0]["keywords"],
                         ["child obedient parent", "kid blank face"])
        self.assertEqual(scenes[1]["keywords"], ["classroom kids cleaning"])

    def test_screen_directions_fallback(self):
        md = SAMPLE_MD.split("## 3.")[0]  # 표 제거
        self.assertEqual(rv.parse_broll_table(md), [])
        scenes = rv.parse_screen_directions(md)
        self.assertEqual(len(scenes), 1)
        self.assertIn("클로즈업", scenes[0]["scene"])

    def test_narration(self):
        self.assertIn("말을 잘 듣는다고요", rv.extract_narration(SAMPLE_MD))


class TestPrompts(unittest.TestCase):
    def test_fallback_without_llm(self):
        scenes = rv.parse_broll_table(SAMPLE_MD)
        prompts = rv.build_prompts(scenes, use_llm=False)
        self.assertEqual(len(prompts), 2)
        self.assertIn("child obedient parent", prompts[0])
        self.assertIn("no text", prompts[0])

    def test_llm_prompts(self):
        scenes = rv.parse_broll_table(SAMPLE_MD)
        with mock.patch.object(rv.llm, "call_json",
                               return_value={"prompts": ["p1", "p2"]}):
            self.assertEqual(rv.build_prompts(scenes), ["p1", "p2"])

    def test_llm_mismatch_falls_back(self):
        scenes = rv.parse_broll_table(SAMPLE_MD)
        with mock.patch.object(rv.llm, "call_json", return_value={"prompts": ["only1"]}):
            prompts = rv.build_prompts(scenes)
        self.assertEqual(len(prompts), 2)
        self.assertIn("no text", prompts[0])


class TestMuapi(unittest.TestCase):
    def _resp(self, status=200, body=None):
        r = mock.Mock()
        r.status_code = status
        r.json.return_value = body or {}
        r.text = json.dumps(body or {})
        r.raise_for_status = mock.Mock()
        return r

    def test_submit_and_poll(self):
        with mock.patch.object(rv.config, "MUAPI_API_KEY", "k"), \
             mock.patch.object(rv, "POLL_SECONDS", 0), \
             mock.patch.object(rv.requests, "post",
                               return_value=self._resp(body={"request_id": "r1"})) as post, \
             mock.patch.object(rv.requests, "get", side_effect=[
                 self._resp(body={"status": "processing"}),
                 self._resp(body={"status": "completed",
                                  "outputs": ["https://cdn/x.mp4"]}),
             ]):
            rid = rv.submit_video("p", "seedance-lite-t2v", "720p", 5)
            self.assertEqual(rid, "r1")
            self.assertIn("seedance-lite-t2v", post.call_args.args[0])
            self.assertEqual(post.call_args.kwargs["json"]["aspect_ratio"], "9:16")
            self.assertEqual(rv.poll_result("r1"), "https://cdn/x.mp4")

    def test_poll_failure_raises(self):
        with mock.patch.object(rv.config, "MUAPI_API_KEY", "k"), \
             mock.patch.object(rv, "POLL_SECONDS", 0), \
             mock.patch.object(rv.requests, "get",
                               return_value=self._resp(body={"status": "failed",
                                                             "error": "nsfw"})):
            with self.assertRaises(RuntimeError):
                rv.poll_result("r1")

    def test_missing_key(self):
        with mock.patch.object(rv.config, "MUAPI_API_KEY", ""):
            with self.assertRaises(RuntimeError):
                rv.submit_video("p", "m", "720p", 5)

    def test_empty_env_falls_back_to_default_model(self):
        # 워크플로우가 미설정 시크릿을 빈 문자열로 넘겨도 기본 모델을 써야 한다
        # (빈 모델명 → POST /api/v1/ → 404 회귀 방지)
        import importlib
        with mock.patch.dict("os.environ", {
            "DG_REELS_VIDEO_MODEL": "",
            "DG_REELS_VIDEO_RESOLUTION": "",
            "DG_REELS_SCENE_SECONDS": "",
            "DG_REELS_MAX_SCENES": "",
        }):
            cfg = importlib.reload(rv.config)
            self.assertEqual(cfg.REELS_VIDEO_MODEL, "seedance-lite-t2v")
            self.assertEqual(cfg.REELS_VIDEO_RESOLUTION, "720p")
            self.assertEqual(cfg.REELS_SCENE_SECONDS, 5)
            self.assertEqual(cfg.REELS_MAX_SCENES, 7)
        importlib.reload(rv.config)  # 원상 복구


class TestMerge(unittest.TestCase):
    def test_merge_command(self):
        cmd = rv.merge_command([Path("a.mp4"), Path("b.mp4")], Path("out.mp4"))
        self.assertEqual(cmd.count("-i"), 2)
        joined = " ".join(cmd)
        self.assertIn("concat=n=2:v=1:a=0", joined)
        self.assertIn("1080:1920", joined)


class TestRunDry(unittest.TestCase):
    def test_dry_run_from_script(self):
        with TemporaryDirectory() as td:
            script = Path(td) / "원고_릴스_훈육_테스트.md"
            script.write_text(SAMPLE_MD, encoding="utf-8")
            out = Path(td) / "out"
            plan = rv.run(script=str(script), out_dir=str(out),
                          dry_run=True, use_llm=False)
            self.assertTrue(plan["dry_run"])
            self.assertEqual(len(plan["scenes"]), 2)
            self.assertTrue(all(s.get("prompt") for s in plan["scenes"]))
            self.assertTrue((out / "reels_plan.json").exists())
            self.assertTrue((out / "notes.md").exists())

    def test_find_script_partial_match(self):
        with TemporaryDirectory() as td:
            review = Path(td) / rv.REVIEW_DIR
            review.mkdir(parents=True)
            (review / "원고_릴스_훈육_어쩌구.md").write_text("x", encoding="utf-8")
            with mock.patch.dict("os.environ", {"DG_VAULT_ROOT": td}):
                hit = rv.find_script("릴스_훈육")
            self.assertIsNotNone(hit)
            self.assertTrue(hit.name.endswith("어쩌구.md"))


if __name__ == "__main__":
    unittest.main()
