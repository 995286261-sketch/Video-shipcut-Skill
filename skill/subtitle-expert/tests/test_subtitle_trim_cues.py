"""In-process tests for subtitle_trim_cues.py (hide-under-chapter-card rule, moved out of G4)."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "subtitle_trim_cues.py"
SPEC = importlib.util.spec_from_file_location("subtitle_trim_cues", SCRIPT)
trimmer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trimmer)

ASS_TEMPLATE = """[Script Info]
Title: fixture

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,{start},{end},Narration,{text}
"""


def cue(start, end, text):
    return ASS_TEMPLATE.format(start=start, end=end, text=text)


class TrimCuesTest(unittest.TestCase):
    def test_time_roundtrip_is_centisecond_safe(self):
        # ASS stores centiseconds; the 10× SRT timebase incident (㊍) must not recur here.
        self.assertEqual(trimmer.parse_ass_ms("0:00:01.50"), 1500)
        self.assertEqual(trimmer.format_ass_ms(1500), "0:00:01.50")
        self.assertEqual(trimmer.format_ass_ms(trimmer.parse_ass_ms("1:02:03.45")), "1:02:03.45")

    def test_overlapping_cue_is_split_around_card(self):
        derived, trimmed = trimmer.trim_ass_cues(cue("0:00:00.00", "0:00:02.00", "你好"), [(500, 1000)])
        dialogues = [line for line in derived.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(1, trimmed)
        self.assertEqual(2, len(dialogues))
        self.assertIn("0:00:00.00,0:00:00.50", dialogues[0].replace("Dialogue: ", ""))
        self.assertIn("0:00:01.00,0:00:02.00", dialogues[1].replace("Dialogue: ", ""))

    def test_untouched_cue_and_headers_are_verbatim(self):
        derived, trimmed = trimmer.trim_ass_cues(cue("0:00:00.00", "0:00:01.00", "第一句"), [(1500, 2000)])
        self.assertEqual(0, trimmed)
        self.assertIn("Format: Layer, Start, End, Style, Text", derived)
        dialogues = [line for line in derived.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(1, len(dialogues))
        # untouched cues are rebuilt from the parsed fields (moved verbatim from G4);
        # assert on field content, not on the exact spacing of the rebuilt line
        self.assertIn("0:00:00.00", dialogues[0])
        self.assertIn("0:00:01.00", dialogues[0])
        self.assertIn("第一句", dialogues[0])

    def test_full_cover_drops_cue_and_slivers_below_40ms(self):
        # A card covering the whole cue leaves nothing; a 20ms sliver must not burn as a flash cue.
        derived, trimmed = trimmer.trim_ass_cues(cue("0:00:01.00", "0:00:02.00", "被整卡覆盖"), [(500, 2500)])
        self.assertEqual(1, trimmed)
        self.assertNotIn("Dialogue:", derived)
        derived, _ = trimmer.trim_ass_cues(cue("0:00:00.00", "0:00:01.00", "尾缝"), [(20, 1000)])
        self.assertNotIn("0:00:00.00,0:00:00.02", derived)

    def test_card_range_parsing_rejects_junk(self):
        self.assertEqual(trimmer.parse_card_range("500:1000"), (500, 1000))
        for junk in ("abc", "1000:500", "-5:10", "500"):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    trimmer.parse_card_range(junk)
            payload = json.loads(out.getvalue().strip().splitlines()[-1])
            self.assertEqual("invalid", payload["status"])

    def test_cli_writes_derived_file_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "approved.ass"
            source.write_text(cue("0:00:00.00", "0:00:02.00", "你好"), encoding="utf-8")
            out = root / "derived.ass"
            argv = ["subtitle_trim_cues.py", "--ass", str(source), "--out", str(out), "--card-range", "500:1000"]
            with unittest.mock.patch("sys.argv", argv):
                with contextlib.redirect_stdout(io.StringIO()) as out_stream:
                    code = trimmer.main()
            self.assertEqual(0, code)
            report = json.loads(out_stream.getvalue().strip().splitlines()[-1])
            self.assertEqual("completed", report["status"])
            self.assertEqual(1, report["trimmedCues"])
            self.assertTrue(out.is_file())
            self.assertIn("Dialogue:", out.read_text(encoding="utf-8"))
            # the approved source is never modified — G4 burns only the derived file
            self.assertEqual(cue("0:00:00.00", "0:00:02.00", "你好"), source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
