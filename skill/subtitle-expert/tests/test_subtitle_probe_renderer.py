import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/subtitle-expert/scripts/subtitle_probe_renderer.py"

_spec = importlib.util.spec_from_file_location("subtitle_probe_renderer", SCRIPT)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def run_main(argv):
    buffer = io.StringIO()
    saved = sys.argv
    sys.argv = ["subtitle_probe_renderer", *argv]
    try:
        with contextlib.redirect_stdout(buffer):
            try:
                code = probe.main()
            except SystemExit as error:
                code = error.code if isinstance(error.code, int) else 2
    finally:
        sys.argv = saved
    return code, buffer.getvalue()


class SubtitleProbeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.have_ffmpeg = shutil.which("ffmpeg") is not None

    def test_auto_wrap_true_without_evidence_is_refused(self):
        code, output = run_main(["--output-dir", str(self.root), "--auto-wrap", "true"])
        self.assertEqual(2, code)
        payload = json.loads(output)
        self.assertEqual("invalid", payload["status"])
        self.assertIn("auto-wrap-evidence", payload["error"])

    def test_conservative_profile_lands_on_disk(self):
        if not self.have_ffmpeg:
            self.skipTest("ffmpeg required for the probe")
        code, output = run_main(["--output-dir", str(self.root)])
        self.assertEqual(0, code, output)
        payload = json.loads(output)
        self.assertEqual("completed", payload["status"])
        self.assertFalse(payload["autoWrap"])
        profile = json.loads((self.root / "字幕-渲染器能力档-v0.1.json").read_text(encoding="utf-8"))
        self.assertEqual("subtitle-expert", profile["skill"])
        self.assertIs(profile["autoWrap"]["value"], False)
        self.assertIn("conservative default", profile["autoWrap"]["basis"])

    def test_evidenced_auto_wrap_is_recorded_verbatim(self):
        if not self.have_ffmpeg:
            self.skipTest("ffmpeg required for the probe")
        code, output = run_main(["--output-dir", str(self.root), "--auto-wrap", "true",
                                 "--auto-wrap-evidence", "宿主实测：见 failure-samples/autowrap-note.md"])
        self.assertEqual(0, code, output)
        profile = json.loads((self.root / "字幕-渲染器能力档-v0.1.json").read_text(encoding="utf-8"))
        self.assertIs(profile["autoWrap"]["value"], True)
        self.assertIn("宿主实测", profile["autoWrap"]["evidence"])
        self.assertEqual("measured evidence", profile["autoWrap"]["basis"])

    def test_libass_banner_parsing_never_reads_configuration_flags_as_versions(self):
        # 09-21 实测抓到：WorkTool ffmpeg 无独立 libass 版本行，旧正则把
        # "--enable-libass --enable-libfreetype" 的下一个 token 当成了版本号。
        worktool_banner = ("ffmpeg n7.0.1\n  configuration: --enable-gpl --enable-libass "
                          "--enable-libfreetype --enable-libx264\n")
        parsed = probe.parse_version_output(worktool_banner)
        self.assertTrue(parsed["libassEnabled"])
        self.assertNotIn("--", parsed["libass"])
        self.assertTrue(parsed["libass"].startswith("unknown"))
        with_version = "ffmpeg 6.1\nlibass 0.17.3\n  configuration: --enable-libass\n"
        parsed = probe.parse_version_output(with_version)
        self.assertEqual("0.17.3", parsed["libass"])
        self.assertTrue(parsed["libassEnabled"])
        parsed = probe.parse_version_output("ffmpeg 6.1\n  configuration: --enable-libx264\n")
        self.assertEqual("absent", parsed["libass"])
        self.assertFalse(parsed["libassEnabled"])


if __name__ == "__main__":
    unittest.main()
