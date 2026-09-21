import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "transition_probe_host.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("transition_probe_host", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load_probe()

REAL_HELP_SAMPLE = """ffmpeg version 7.0 Copyright (c) 2024 the FFmpeg developers
  built with Apple clang
  configuration: --enable-libass --enable-libfreetype
Graphing filters take a per-pixel option.
xfade cross fade 2 video inputs
    transition        <int>        ..FV....... set cross fade transition (from -1 to 57) (default fade)
     custom          -1           ..FV....... custom transition
     fade            0            ..FV....... fade transition
     wipeleft        1            ..FV....... wipe left transition
     dissolve       13            ..FV....... dissolve transition
     fadeblack      15            ..FV....... fade to black transition
"""


class ParseTests(unittest.TestCase):
    def test_version_banner_parsed_without_confusing_configuration_line(self):
        facts = probe.parse_version_banner(REAL_HELP_SAMPLE)
        self.assertEqual(facts["version"], "7.0")
        self.assertTrue(facts["versionLine"].startswith("ffmpeg version 7.0"))

    def test_missing_version_is_unknown_not_guessed(self):
        self.assertEqual(probe.parse_version_banner("garbage")["version"], "unknown")

    def test_xfade_names_parsed_from_constant_rows(self):
        names = probe.parse_xfade_names(REAL_HELP_SAMPLE)
        self.assertEqual(names, ["dissolve", "fade", "fadeblack", "wipeleft"])  # custom 被剔除、非名单行不误收

    def test_empty_help_gives_no_names(self):
        self.assertEqual(probe.parse_xfade_names(""), [])


class MainTests(unittest.TestCase):
    def run_main(self, argv):
        stdout = io.StringIO()
        backup = sys.argv
        sys.argv = ["transition_probe_host.py"] + argv
        try:
            with contextlib.redirect_stdout(stdout):
                try:
                    code = probe.main()
                except SystemExit as exit_signal:
                    code = exit_signal.code
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue())

    def test_probe_writes_profile_when_ffmpeg_present(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            code, report = self.run_main(["--output-dir", tmp])
            self.assertEqual(code, 0, report)
            profile = json.loads(Path(report["profile"]).read_text(encoding="utf-8"))
            self.assertEqual(profile["skill"], "transition-expert")
            self.assertEqual(profile["purpose"], "transition_host_profile")
            self.assertTrue(profile["xfade"]["available"])
            self.assertIn("dissolve", profile["xfade"]["transitions"])
            self.assertTrue(profile["capabilities"]["dissolve"])
            self.assertTrue(profile["basis"].startswith("measured probe"))


if __name__ == "__main__":
    unittest.main()
