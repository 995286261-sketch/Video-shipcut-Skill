"""In-process tests for subtitle_convert.py (ASS→SRT sole derivation path, ⑭ sub-item 4)."""
import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "subtitle_convert.py"
SPEC = importlib.util.spec_from_file_location("subtitle_convert", SCRIPT)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)

ASS_HEADER = """[Script Info]
Title: fixture

[V4+ Styles]
Format: Name, Fontname
Style: Narration,Arial

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(tmp: Path, events: str) -> Path:
    path = tmp / "G3-字幕时间轴-v0.9.ass"
    path.write_text(ASS_HEADER + events, encoding="utf-8")
    return path


def run(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        try:
            code = converter.main(argv)
        except SystemExit as exit_error:
            code = exit_error.code
    return code, json.loads(buffer.getvalue() or "{}")


class ConvertHappyTests(unittest.TestCase):
    def test_conversion_is_byte_exact_and_reports_sha(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, (
                "Dialogue: 0,0:00:07.00,0:00:11.41,Narration,,0,0,0,,In the Universal Century.\n"
                "Dialogue: 0,0:00:16.50,0:00:23.44,Narration,,0,0,0,,Goddess of Fate:\\Nsecond answer.\n"
            ))
            out = tmp / "G3-字幕时间轴-v0.9.srt"
            code, payload = run(["--ass", str(ass), "--out", str(out)])
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["cues"], 2)
            self.assertEqual(payload["sourceSha256"],
                             hashlib.sha256(ass.read_bytes()).hexdigest().upper())
            self.assertEqual(out.read_text(encoding="utf-8"), (
                "1\n00:00:07,000 --> 00:00:11,410\nIn the Universal Century.\n"
                "\n"
                "2\n00:00:16,500 --> 00:00:23,440\nGoddess of Fate:\nsecond answer.\n"
            ))

    def test_default_out_sits_next_to_ass_with_same_stem(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, "Dialogue: 0,0:00:01.00,0:00:02.00,Narration,,0,0,0,,hi\n")
            code, payload = run(["--ass", str(ass)])
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["srt"], str(tmp / "G3-字幕时间轴-v0.9.srt"))

    def test_centisecond_boundaries_are_exact_integers(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, (
                "Dialogue: 0,0:01:23.99,0:01:24.00,Narration,,0,0,0,,edge\n"
                "Dialogue: 0,1:02:03.04,2:00:00.00,Narration,,0,0,0,,long\n"
            ))
            out = tmp / "o.srt"
            code, payload = run(["--ass", str(ass), "--out", str(out)])
            self.assertEqual(code, 0, payload)
            text = out.read_text(encoding="utf-8")
            self.assertIn("00:01:23,990 --> 00:01:24,000", text)
            self.assertIn("01:02:03,040 --> 02:00:00,000", text)

    def test_override_tags_stripped_and_comments_skipped_order_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, (
                "Comment: 0,0:00:01.00,0:00:02.00,Narration,,0,0,0,,not delivered\n"
                "Dialogue: 2,0:00:01.00,0:00:02.00,Narration,,0,0,0,,{\\an8}styled line\n"
                "Dialogue: 0,0:00:03.00,0:00:04.00,Narration,,0,0,0,,plain\n"
            ))
            out = tmp / "o.srt"
            code, payload = run(["--ass", str(ass), "--out", str(out)])
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["cues"], 2)
            text = out.read_text(encoding="utf-8")
            self.assertIn("styled line", text)
            self.assertNotIn("not delivered", text)
            self.assertNotIn("{", text)
            self.assertTrue(text.startswith("1\n"), "write order preserved, layer ignored")


class ConvertStrikeTests(unittest.TestCase):
    def test_start_not_before_end_is_invalid(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, "Dialogue: 0,0:00:05.00,0:00:05.00,Narration,,0,0,0,,x\n")
            code, payload = run(["--ass", str(ass), "--out", str(tmp / "o.srt")])
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "invalid")
            self.assertIn("start", payload["error"])

    def test_missing_events_section_is_invalid(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = tmp / "not-ass.srt"
            ass.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
            code, payload = run(["--ass", str(ass), "--out", str(tmp / "o.srt")])
            self.assertEqual(code, 2)
            self.assertIn("[Events]", payload["error"])

    def test_no_dialogue_events_is_invalid(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, "Comment: 0,0:00:01.00,0:00:02.00,Narration,,0,0,0,,x\n")
            code, payload = run(["--ass", str(ass), "--out", str(tmp / "o.srt")])
            self.assertEqual(code, 2)
            self.assertIn("no Dialogue", payload["error"])

    def test_malformed_time_is_invalid(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, "Dialogue: 0,0:00:07,000,0:00:11,410,Narration,,0,0,0,,srt time leaked in\n")
            code, payload = run(["--ass", str(ass), "--out", str(tmp / "o.srt")])
            self.assertEqual(code, 2)
            self.assertIn("cannot parse ASS time", payload["error"])

    def test_tag_only_text_is_invalid(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ass = write_ass(tmp, "Dialogue: 0,0:00:01.00,0:00:02.00,Narration,,0,0,0,,{\\an8}\n")
            code, payload = run(["--ass", str(ass), "--out", str(tmp / "o.srt")])
            self.assertEqual(code, 2)
            self.assertIn("no visible text", payload["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
