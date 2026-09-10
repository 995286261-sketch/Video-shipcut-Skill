#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ANALYZE = SKILL / "scripts" / "music_analyze.py"
PYTHON = os.environ.get("P0C_PYTHON_BIN") or sys.executable


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


class MusicAnalyzeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_script(self, args, env=None):
        full_env = dict(os.environ)
        if env is not None:
            full_env.update(env)
        return subprocess.run([PYTHON, str(ANALYZE), *args], capture_output=True, text=True,
                              encoding="utf-8", env=full_env)

    def write_clicks(self, name="clicks.wav", period=0.5, seconds=6):
        target = self.root / name
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"aevalsrc=0.6*sin(2*PI*1000*t)*lt(mod(t\\,{period})\\,0.02)|0:d={seconds}",
                        "-ar", "22050", "-ac", "1", str(target)], check=True, capture_output=True, text=True)
        return target

    def test_missing_runtime_is_structured_block(self):
        if not have("ffmpeg") or not have("ffprobe"):
            self.skipTest("ffmpeg/ffprobe required")
        wav = self.write_clicks()
        missing = str(self.root / "no-such-runtime")
        result = self.run_script(["--input", str(wav), "--output-dir", str(self.root / "out")],
                                 env={"MUSIC_EXPERT_RUNTIME_HOME": missing,
                                      "P0C_MUSIC_RUNTIME_HOME": missing})
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_analysis_runtime", payload["blockers"][0]["type"])

    def test_empty_input_is_invalid(self):
        empty = self.root / "empty.wav"
        empty.write_bytes(b"")
        result = self.run_script(["--input", str(empty), "--output-dir", str(self.root / "out")])
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", payload["status"])

    def test_no_audio_stream_is_invalid(self):
        if not have("ffmpeg"):
            self.skipTest("ffmpeg required")
        video = self.root / "silent.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
                        "-frames:v", "5", str(video)], check=True, capture_output=True, text=True)
        result = self.run_script(["--input", str(video), "--output-dir", str(self.root / "out")])
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", payload["status"])

    def test_positive_analysis_and_cache_hit(self):
        for tool in ("ffmpeg", "ffprobe"):
            if not have(tool):
                self.skipTest(f"{tool} required")
        env_home = os.environ.get("MUSIC_EXPERT_RUNTIME_HOME") or os.environ.get("P0C_MUSIC_RUNTIME_HOME")
        if not env_home:
            self.skipTest("MUSIC_EXPERT_RUNTIME_HOME (music-expert runtime) not configured")
        wav = self.write_clicks()
        out = self.root / "out"
        first = self.run_script(["--input", str(wav), "--output-dir", str(out),
                                 "--style-brief-out", str(out / "brief.json")])
        payload = json.loads(first.stdout)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        self.assertEqual("completed", payload["status"])
        report = Path(payload["report"])
        self.assertTrue(report.is_file() and report.stat().st_size > 0)
        data = json.loads(report.read_text(encoding="utf-8"))
        tempo = data["tempoBpm"]
        # 120 BPM clicks; tolerate the inherent octave ambiguity of beat tracking.
        self.assertTrue(any(abs(tempo - anchor) <= 8 for anchor in (60, 120, 240)),
                        f"tempo {tempo} not near a 120 BPM octave")
        self.assertTrue(data["hitPoints"], "卡点表 must not be empty")
        self.assertGreaterEqual(len(data["energySegments"]), 1)
        brief = json.loads((out / "brief.json").read_text(encoding="utf-8"))
        # G1 field test: ducking-heavy reference soundtracks must not smuggle the raw
        # short-term curve in as "music energy shape" — the brief carries a bucket curve.
        self.assertLessEqual(brief["shapeBuckets"], 16)
        self.assertEqual(brief["shapeBuckets"], len(brief["energyShape"]))
        self.assertEqual(brief["shapeBucketMs"], round(brief["durationMs"] / brief["shapeBuckets"]))
        # the fixed-table echo card is a standard product of every fresh analysis
        echo = Path(payload["echo"])
        self.assertTrue(echo.is_file() and echo.stat().st_size > 0)
        card = echo.read_text(encoding="utf-8")
        self.assertIn("# BGM 分析回显", card)
        self.assertIn("| 段 | 区间 | 能量 | 音乐结构 | 对剪辑的意义 |", card)
        # Issue 031: same bytes + same analysis version must reuse, never recompute.
        second = self.run_script(["--input", str(wav), "--output-dir", str(out)])
        hit = json.loads(second.stdout)
        self.assertEqual("cache_hit", hit["status"])
        self.assertEqual(str(echo), hit["echo"])
        # a deleted card is re-rendered from the cached JSON (pure stdlib, free)
        echo.unlink()
        third = self.run_script(["--input", str(wav), "--output-dir", str(out)])
        self.assertEqual("cache_hit", json.loads(third.stdout)["status"])
        self.assertTrue(echo.is_file() and echo.stat().st_size > 0)
        # N1 rule: a cache hit from a foreign --cache-root is relocated byte-identically
        # so the requested output directory (e.g. a 素材包 slot) stays self-contained
        elsewhere = self.root / "slot"
        fourth = self.run_script(["--input", str(wav), "--output-dir", str(elsewhere), "--cache-root", str(out)])
        hit = json.loads(fourth.stdout)
        self.assertEqual("cache_hit", hit["status"])
        self.assertEqual(elsewhere, Path(hit["report"]).parent)
        self.assertEqual(report.read_bytes(), Path(hit["report"]).read_bytes())
        self.assertEqual(elsewhere, Path(hit["echo"]).parent)
        # G1 rule: a cache hit still derives the requested brief (pure stdlib re-derivation)
        brief_again = self.root / "brief-reuse.json"
        fifth = self.run_script(["--input", str(wav), "--output-dir", str(elsewhere), "--cache-root", str(out),
                                 "--style-brief-out", str(brief_again)])
        hit5 = json.loads(fifth.stdout)
        self.assertEqual("cache_hit", hit5["status"])
        self.assertEqual(str(brief_again), hit5["styleBrief"])
        self.assertEqual(brief, json.loads(brief_again.read_text(encoding="utf-8")))


class EchoCardSourceTest(unittest.TestCase):
    """G1 noise rule: a video soundtrack card must say its numbers are mixed-audio facts."""

    def setUp(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        import music_echo
        self.music_echo = music_echo

    def card(self, media_kind):
        report = {
            "source": {"path": "ref.mp4", "mediaKind": media_kind, "decodedDurationMs": 60000, "sha256": "0" * 64},
            "analysisVersion": "test", "tempoBpm": 120.0, "beatsMs": [0, 500, 1000],
            "hitPoints": [{"tMs": 0, "kind": "beat"}, {"tMs": 260, "kind": "accent"}],
            "energySegments": [{"startMs": 0, "endMs": 60000, "energyMean": 0.2}],
            "loudness": {"integratedLufs": -13.4},
        }
        return self.music_echo.render_card(report)

    def test_video_source_card_carries_mixed_audio_warning(self):
        card = self.card("video-with-audio")
        self.assertIn("解说混音后的事实", card)
        self.assertIn("音轨抽自视频", card)

    def test_pure_audio_card_has_no_warning(self):
        self.assertNotIn("解说混音后的事实", self.card("audio"))


if __name__ == "__main__":
    unittest.main()
