import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/video-edit-plan/scripts/validate_g3_subtitle_layout.py"
PYTHON = sys.executable

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: NarrMain,PingFang SC,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,2,20,20,58,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


class SubtitleLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.write_text(value, encoding="utf-8")
        return path

    def ass(self, fontsize, *dialogues):
        lines = [ASS_HEADER.format(fontsize=fontsize)]
        for index, text in enumerate(dialogues):
            lines.append(f"Dialogue: 0,0:00:{index:02d}.00,0:00:{index + 1:02d}.00,NarrMain,,0,0,0,,{text}")
        return self.write("captions.ass", "\n".join(lines) + "\n")

    def layout(self, **overrides):
        lane = {"zone": "70-84% height", "maxLines": 2, "fontsize": 14}
        lane.update(overrides.pop("lane", {}))
        value = {"schemaVersion": "0.1", "node": "G3", "projectId": "demo-001", "lanes": {"narration": lane}}
        value.update(overrides)
        return self.write("layout.json", json.dumps(value, ensure_ascii=False))

    def run_cli(self, ass, layout):
        result = subprocess.run([PYTHON, str(SCRIPT), "--ass", str(ass), "--layout", str(layout)], capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout + result.stderr

    def test_two_broken_lines_within_contract_pass(self):
        ass = self.ass(14, "从 NZ 开头的番号就能看出它的血脉：\\N它是在第一次新吉翁战争时期投入实战的机体。")
        code, output = self.run_cli(ass, self.layout())
        self.assertEqual(0, code, output)
        self.assertIn('"maxRenderedLinesObserved": 2', output)

    def test_fontsize_drift_from_contract_is_rejected(self):
        ass = self.ass(20, "短句一条。")
        code, output = self.run_cli(ass, self.layout())
        self.assertNotEqual(0, code)
        self.assertIn("differs from layout contract fontsize", output)

    def test_single_run_wrapping_to_three_lines_is_rejected(self):
        ass = self.ass(14, "句" * 100)
        code, output = self.run_cli(ass, self.layout())
        self.assertNotEqual(0, code)
        self.assertIn("needs 3 rendered lines", output)

    def test_hard_breaks_beyond_max_lines_are_rejected(self):
        ass = self.ass(14, "第一行\\N第二行\\N第三行")
        code, output = self.run_cli(ass, self.layout())
        self.assertNotEqual(0, code)
        self.assertIn("needs 3 rendered lines", output)

    def test_missing_max_lines_in_contract_is_rejected(self):
        contract = self.layout()
        value = json.loads(contract.read_text(encoding="utf-8"))
        del value["lanes"]["narration"]["maxLines"]
        contract.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        ass = self.ass(14, "短句一条。")
        code, output = self.run_cli(ass, contract)
        self.assertNotEqual(0, code)
        self.assertIn("maxLines", output)

    def test_timeline_without_events_is_rejected(self):
        ass = self.ass(14)
        code, output = self.run_cli(ass, self.layout())
        self.assertNotEqual(0, code)
        self.assertIn("no dialogue events", output)


if __name__ == "__main__":
    unittest.main()
