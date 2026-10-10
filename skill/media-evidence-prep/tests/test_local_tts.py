import contextlib
import importlib.util
import io
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

_spec = importlib.util.spec_from_file_location("local_tts", SCRIPT)
tts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts)


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


STUB_SAY_SILENT = """if [ "$2" = "?" ]; then echo "StubVoice          en_US"; exit 0; fi
exit 0
"""

STUB_SAY_CRASH = """if [ "$2" = "?" ]; then echo "StubVoice          en_US"; exit 0; fi
echo "stub boom" >&2
exit 3
"""


class LocalTtsFailureTraceTests(unittest.TestCase):
    """⑭小6 (banshee Daniel incident): a failed synthesis run must leave a versioned
    failure manifest on disk instead of nothing; failure manifests share the -vN series.

    In-process pattern (module.main + injected sys.argv, as in subtitle/music suites):
    a stubbed `say` is placed first on PATH so the synthesis itself fails deterministically.
    """

    def setUp(self):
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg/ffprobe must be on PATH for the tool's preflight")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.out = self.root / "narration"
        self.sentences_path = self.root / "sentences.json"
        self.sentences_path.write_text(json.dumps([
            {"sentenceId": "s1", "text": "第一句。"},
            {"sentenceId": "s2", "text": "第二句。"},
        ], ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_stubbed(self, stub_body):
        stub = self.bin / "say"
        stub.write_text("#!/bin/sh\n" + stub_body, encoding="utf-8")
        stub.chmod(0o755)
        saved_path = os.environ["PATH"]
        saved_argv = sys.argv
        os.environ["PATH"] = str(self.bin) + os.pathsep + saved_path
        sys.argv = ["local_tts", "--sentences", str(self.sentences_path),
                    "--voice", "StubVoice", "--output-dir", str(self.out)]
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                try:
                    code = tts.main()
                except SystemExit as error:
                    code = error.code if isinstance(error.code, int) else 2
        finally:
            os.environ["PATH"] = saved_path
            sys.argv = saved_argv
        return code, buffer.getvalue()

    def test_silent_failure_leaves_versioned_trace(self):
        code, output = self.run_stubbed(STUB_SAY_SILENT)
        self.assertEqual(1, code, output)
        payload = json.loads(output)
        self.assertEqual("failed", payload["status"])
        self.assertIn("say exited without producing", payload["error"])
        manifest_path = Path(payload["failureManifest"])
        self.assertTrue(manifest_path.is_file())
        self.assertEqual("G2-配音清单-v0.1.json", manifest_path.name)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("failed", manifest["status"])
        self.assertEqual("narration_synthesis_failure_record", manifest["purpose"])
        self.assertEqual("s1", manifest["failedAt"])
        self.assertEqual(2, manifest["sentencesRequested"])
        self.assertEqual([], manifest["sentencesCompleted"])
        self.assertEqual("StubVoice", manifest["voice"])

    def test_crash_exit_records_stderr_verbatim(self):
        code, output = self.run_stubbed(STUB_SAY_CRASH)
        self.assertEqual(1, code, output)
        payload = json.loads(output)
        self.assertIn("say exited 3", payload["error"])
        manifest = json.loads(Path(payload["failureManifest"]).read_text(encoding="utf-8"))
        self.assertIn("say exited 3", manifest["error"])
        self.assertIn("stub boom", manifest["error"])

    def test_failure_rerun_appends_version_and_keeps_old(self):
        first_code, first_output = self.run_stubbed(STUB_SAY_SILENT)
        first_bytes = Path(json.loads(first_output)["failureManifest"]).read_bytes()
        second_code, second_output = self.run_stubbed(STUB_SAY_SILENT)
        self.assertEqual((1, 1), (first_code, second_code))
        first_path = Path(json.loads(first_output)["failureManifest"])
        second_path = Path(json.loads(second_output)["failureManifest"])
        self.assertEqual("G2-配音清单-v0.1.json", first_path.name)
        self.assertEqual("G2-配音清单-v0.2.json", second_path.name)
        self.assertEqual(first_bytes, first_path.read_bytes())  # old trace untouched
        self.assertEqual("v0.1", json.loads(first_output)["manifestVersion"])
        self.assertEqual("v0.2", json.loads(second_output)["manifestVersion"])


if __name__ == "__main__":
    unittest.main()
