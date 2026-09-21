"""In-process tests for subtitle_check_srt.py (delivery-side SRT QA; ㊍ now has an owner)."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "subtitle_check_srt.py"
SPEC = importlib.util.spec_from_file_location("subtitle_check_srt", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

VALID_SRT = "1\n00:00:00,000 --> 00:00:01,000\n你好\n\n2\n00:00:01,000 --> 00:00:02,500\n世界\n"


class CheckSrtTest(unittest.TestCase):
    def run_cli(self, path):
        with unittest.mock.patch("sys.argv", ["subtitle_check_srt.py", str(path)]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = checker.main()
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_valid_file_passes_with_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "subtitles.srt"
            path.write_text(VALID_SRT, encoding="utf-8")
            code, report = self.run_cli(path)
            self.assertEqual(0, code)
            self.assertEqual("passed", report["status"])
            self.assertEqual(2, report["cues"])
            self.assertEqual(2500, report["lastEndMs"])
            self.assertEqual(64, len(report["sha256"]))

    def test_10x_timebase_slip_is_caught_as_overlap(self):
        # ㊍ shape: one cue's milliseconds written ×10 apart from its neighbour.
        cues, errors = checker.check_srt("1\n00:00:00,000 --> 00:01:00,000\n第一句\n\n2\n00:00:02,000 --> 00:00:04,000\n第二句\n")
        self.assertEqual(2, len(cues))
        self.assertTrue(any("overlaps" in error for error in errors))

    def test_bad_timestamp_format_rejected(self):
        # Non-padded or colon-ms style must fail (G5's old regex only demanded "any" line match).
        _, errors = checker.check_srt("1\n0:0:1,0 --> 0:0:2,0\n字\n")
        self.assertTrue(any("HH:MM:SS,mmm" in error for error in errors))

    def test_index_and_whitespace_only_cue_errors(self):
        # A whitespace-only text line is swallowed by the blank-line block split, so the
        # honest failure for such a cue is the structural one; index drift is caught per block.
        _, errors = checker.check_srt("2\n00:00:00,000 --> 00:00:01,000\n字\n\n1\n00:00:01,000 --> 00:00:02,000\n   \n\n2\n00:00:02,000 --> 00:00:03,000\n好\n")
        joined = " ".join(errors)
        self.assertIn("index line", joined)
        self.assertIn("expected an index, a timestamp line, and text", joined)

    def test_missing_file_reports_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            code, report = self.run_cli(Path(temp) / "absent.srt")
            self.assertEqual(2, code)
            self.assertEqual("invalid", report["status"])


if __name__ == "__main__":
    unittest.main()
