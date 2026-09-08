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
        result = self.run_script(["--input", str(wav), "--output-dir", str(self.root / "out")],
                                 env={"P0C_MUSIC_RUNTIME_HOME": str(self.root / "no-such-runtime")})
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
        env_home = os.environ.get("P0C_MUSIC_RUNTIME_HOME")
        if not env_home:
            self.skipTest("P0C_MUSIC_RUNTIME_HOME (music-expert runtime) not configured")
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
        self.assertTrue((out / "brief.json").is_file())
        # Issue 031: same bytes + same analysis version must reuse, never recompute.
        second = self.run_script(["--input", str(wav), "--output-dir", str(out)])
        self.assertEqual("cache_hit", json.loads(second.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
