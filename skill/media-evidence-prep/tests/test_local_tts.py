import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/media-evidence-prep/scripts/local_tts.py"
PYTHON = sys.executable


def installed_voices():
    if shutil.which("say") is None:
        return None
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return None
    voices = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and "_" in parts[1].split(" ")[0]:
            name = line.strip()[: line.strip().index(parts[1].split(" ")[0])].strip()
            voices[name] = parts[1].split(" ")[0]
    return voices


class LocalTtsTests(unittest.TestCase):
    """Issues 011/015/017/028: voice pre-check, CAF->wav conversion, measured durations."""

    def setUp(self):
        if shutil.which("say") is None or shutil.which("ffmpeg") is None:
            self.skipTest("macOS say and ffmpeg are required")
        self.voices = installed_voices()
        if not self.voices:
            self.skipTest("cannot enumerate installed voices")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def sentences(self, *texts):
        path = self.root / "sentences.json"
        path.write_text(json.dumps([{"sentenceId": f"s{index}", "text": text} for index, text in enumerate(texts, 1)], ensure_ascii=False), encoding="utf-8")
        return path

    def run_cli(self, args, env=None):
        return subprocess.run([PYTHON, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=env)

    def test_uninstalled_voice_is_blocked(self):
        result = self.run_cli(("--sentences", str(self.sentences("测试句子")), "--voice", "NoSuchVoice999", "--output-dir", str(self.root)))
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_voice", payload["blockers"][0]["type"])

    def test_sentences_are_synthesized_with_measured_durations(self):
        chinese = [name for name, tag in self.voices.items() if tag.startswith("zh")]
        if not chinese:
            self.skipTest("no Chinese voice installed")
        out = self.root / "narration"
        out.mkdir()
        result = self.run_cli(("--sentences", str(self.sentences("这台机体叫作刹帝利。", "它的编号是六六六。")), "--voice", chinese[0], "--output-dir", str(out)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("completed", payload["status"])
        self.assertEqual("preview_only", payload["voiceTier"])
        manifest = json.loads(Path(payload["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(2, len(manifest["sentences"]))
        total = 0
        for item in manifest["sentences"]:
            wav = Path(item["file"])
            self.assertTrue(wav.is_file() and wav.stat().st_size > 0, str(wav))
            self.assertGreater(item["durationMs"], 100)
            total += item["durationMs"]
        self.assertEqual(total, manifest["measuredTotalDurationMs"])

    def test_asr_readback_detects_misread_voice(self):
        chinese = [name for name, tag in self.voices.items() if tag.startswith("zh")]
        runtime = os.environ.get("P0C_FASTER_WHISPER_HOME")
        model_home = os.environ.get("P0C_FASTER_WHISPER_MODEL_HOME")
        if not chinese or not runtime or not model_home:
            self.skipTest("requires a Chinese voice plus the controlled Faster-Whisper runtime")
        out = self.root / "verified"
        out.mkdir()
        result = self.run_cli((
            "--sentences", str(self.sentences("这台机体非常巨大。")), "--voice", chinese[0],
            "--output-dir", str(out), "--verify-asr", "--asr-initial-prompt", "机体, 巨大",
        ))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        manifest = json.loads(Path(json.loads(result.stdout)["manifest"]).read_text(encoding="utf-8"))
        check = manifest["asrVerification"]["perSentence"][0]
        self.assertGreaterEqual(check["similarity"], 0.6)


if __name__ == "__main__":
    unittest.main()
