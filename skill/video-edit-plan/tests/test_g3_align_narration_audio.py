import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/video-edit-plan/scripts/g3_align_narration_audio.py"
PYTHON = sys.executable


class G3AlignNarrationTests(unittest.TestCase):
    """Issue 014: alignment must fail with structured blocks, never import tracebacks or env workarounds."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.audio = self.root / "narration.wav"
        self.audio.write_bytes(b"fake-audio-bytes-for-hashing")
        self.output = self.root / "alignment.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, extra):
        return subprocess.run([PYTHON, str(SCRIPT), "--audio", str(self.audio), "--output", str(self.output), *extra], capture_output=True, text=True, encoding="utf-8")

    def parse_stdout(self, result):
        self.assertNotEqual("", result.stdout.strip(), "stdout must be structured JSON, not a traceback: " + result.stderr)
        return json.loads(result.stdout)

    def test_missing_audio_is_invalid(self):
        result = subprocess.run([PYTHON, str(SCRIPT), "--audio", str(self.root / "missing.wav"), "--output", str(self.output)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(2, result.returncode)
        payload = self.parse_stdout(result)
        self.assertEqual("invalid", payload["status"])

    def test_missing_model_dir_is_blocked_without_traceback(self):
        result = self.run_cli(("--model-dir", str(self.root / "no-such-dir")))
        self.assertEqual(2, result.returncode)
        payload = self.parse_stdout(result)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_model_dir", payload["blockers"][0]["type"])

    def test_model_dir_without_snapshot_is_blocked(self):
        empty_dir = self.root / "models"
        empty_dir.mkdir()
        result = self.run_cli(("--model-dir", str(empty_dir)))
        self.assertEqual(2, result.returncode)
        payload = self.parse_stdout(result)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_cached_model", payload["blockers"][0]["type"])

    def test_matching_cache_key_reuses_existing_alignment(self):
        digest = hashlib.sha256(self.audio.read_bytes()).hexdigest().upper()
        cache_key = {"sha256": digest, "language": "zh", "model": "small", "device": "cpu", "computeType": "int8", "runtimeVersion": "g3-align-narration-v0.2"}
        self.output.write_text(json.dumps({"schemaVersion": "0.1", "node": "G3", "cacheKey": cache_key, "segments": [{"startMs": 0, "endMs": 1000, "text": "已有对齐"}]}, ensure_ascii=False), encoding="utf-8")
        model_dir = self.root / "models"
        model_dir.mkdir()
        result = self.run_cli(("--model-dir", str(model_dir)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = self.parse_stdout(result)
        self.assertEqual("reused", payload["status"])
        self.assertEqual(1, payload["segments"])


if __name__ == "__main__":
    unittest.main()
