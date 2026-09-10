import json
import subprocess
import sys
import tempfile
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_g3_callback.py"
RENDERER = ROOT / "scripts" / "render_g3_review_card.py"
PYTHON = sys.executable
spec = importlib.util.spec_from_file_location("validate_g3_callback", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class G3CallbackValidatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def plan(self):
        segments = []
        for number, start in enumerate((0, 1000), 1):
            segments.append({"segmentId": f"seg-{number:03}", "startMs": start + 10000, "endMs": start + 11000,
                "outputStartMs": start, "outputEndMs": start + 1000,
                "visualVerification": {"status": "verified"}, "semanticAlignment": {"status": "direct_match"}})
        return self.write("plan.json", {"projectId": "p", "segments": segments})

    def callback(self):
        rows = []
        for number, start in enumerate((0, 1000), 1):
            rows.append({"segmentId": f"seg-{number:03}", "outputStartMs": start, "outputEndMs": start + 1000,
                "outputTimecode": validator.format_review_range(start, start + 1000),
                "narrationText": "口播原文", "sourceStartMs": start + 10000, "sourceEndMs": start + 11000,
                "sourceTimecode": validator.format_review_range(start + 10000, start + 11000),
                "observedVisuals": "实际可见的目标主体", "semanticStatus": "direct_match", "subjectStatus": "target_confirmed",
                "riskSummary": "左上角水印需裁切", "bgmPhrase": "phrase-01", "transitionInstruction": "硬切"})
        return {"schemaVersion": "0.1", "node": "G3", "projectId": "p", "callbackType": "final_review",
            "durationMs": 2000, "columns": ["片段 ID", "输出时间", "对应口播", "源片区间", "用途 / 实际画面观察", "语义匹配 / 主体状态 / 风险", "BGM 乐句", "转场指令"], "rows": rows}

    def run_cli(self, callback, plan=None, alignment=None):
        callback_path = self.write("callback.json", callback)
        command = [PYTHON, str(SCRIPT), "--callback", str(callback_path)]
        if plan:
            command += ["--plan", str(plan)]
        if alignment:
            command += ["--alignment", str(alignment)]
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8")

    def bgm_plan(self):
        plan = json.loads(self.plan().read_text(encoding="utf-8"))
        plan["timelineDurationMs"] = 2000
        for segment in plan["segments"]:
            segment["layoutTier"] = "推进"
        plan["bgmPlan"] = {"trackOffsetMs": 60000, "alignmentRef": "G3-剪辑计划/BGM-对齐建议-v0.2.json"}
        return self.write("plan-bgm.json", plan)

    def alignment_artifact(self, snapped=3, missed=1, ducking=2):
        value = {
            "schemaVersion": "0.2", "purpose": "bgm_alignment",
            "alignment": {"offsetMs": 60000, "timelineMs": 2000},
            "snapped": [] if snapped == 1 else [{"x": i} for i in range(snapped)],
            "missed": [{"x": 0}] if missed else [],
            "ducking": [{"sentenceId": f"N0{i}"} for i in range(1, ducking + 1)],
        }
        return self.write("alignment.json", value)

    def callback_v02(self, **basis_changes):
        value = self.callback()
        value["schemaVersion"] = "0.2"
        for row in value["rows"]:
            row["layoutTier"] = "推进"
        basis = {"alignmentRef": "G3-剪辑计划/BGM-对齐建议-v0.2.json", "trackOffsetMs": 60000,
                 "timelineMs": 2000, "snappedCount": 3, "missedCount": 1, "duckedSentences": 2}
        basis.update(basis_changes)
        value["bgmBasis"] = basis
        return value

    def test_valid_final_callback_passes(self):
        result = self.run_cli(self.callback(), self.plan())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_output_time_field_is_blocked(self):
        value = self.callback()
        del value["rows"][0]["outputStartMs"]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outputStartMs", result.stdout)

    def test_missing_or_mismatched_display_timecode_is_blocked(self):
        value = self.callback()
        del value["rows"][0]["outputTimecode"]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outputTimecode", result.stdout)
        value = self.callback()
        value["rows"][0]["sourceTimecode"] = "00:00.000–00:01.000"
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sourceTimecode", result.stdout)

    def test_review_timecode_formatting(self):
        self.assertEqual("00:00.000", validator.format_review_timecode(0))
        self.assertEqual("00:00.001", validator.format_review_timecode(1))
        self.assertEqual("01:01.234", validator.format_review_timecode(61_234))
        self.assertEqual("61:01.234", validator.format_review_timecode(3_661_234))

    def test_renderer_emits_human_readable_ranges(self):
        callback_path = self.write("callback.json", self.callback())
        plan_path = self.plan()
        output = self.root / "G3-回显卡.md"
        result = subprocess.run([PYTHON, str(RENDERER), "--callback", str(callback_path), "--plan", str(plan_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        card = output.read_text(encoding="utf-8")
        self.assertIn("00:00.000–00:01.000", card)
        self.assertIn("00:10.000–00:11.000", card)
        self.assertIn("确认 G3", card)

    def test_wrong_column_order_is_blocked(self):
        value = self.callback()
        value["columns"].pop()
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixed eight-column", result.stdout)

    def test_three_clips_cannot_cover_longer_timeline(self):
        value = self.callback()
        value["durationMs"] = 105648
        value["rows"] = value["rows"][:1]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one row", result.stdout)

    def test_candidate_placeholder_is_blocked(self):
        value = self.callback()
        value["rows"][0]["bgmPhrase"] = "候选 phrase"
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder", result.stdout)

    def test_semantic_mismatch_is_blocked(self):
        value = self.callback()
        value["rows"][0]["semanticStatus"] = "semantic_mismatch"
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("semanticStatus", result.stdout)

    def test_bgm_card_v02_happy_path(self):
        result = self.run_cli(self.callback_v02(), self.bgm_plan(), self.alignment_artifact())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_bgm_plan_requires_card_v02(self):
        result = self.run_cli(self.callback(), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schemaVersion 0.2", result.stdout)

    def test_bgm_basis_counts_must_match_alignment_artifact(self):
        result = self.run_cli(self.callback_v02(snappedCount=9), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snap counts", result.stdout)
        result = self.run_cli(self.callback_v02(duckedSentences=5), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duckedSentences", result.stdout)

    def test_bgm_basis_offset_must_match_plan(self):
        result = self.run_cli(self.callback_v02(trackOffsetMs=61000), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trackOffsetMs", result.stdout)

    def test_row_layout_tier_must_match_plan_and_vocabulary(self):
        value = self.callback_v02()
        value["rows"][0]["layoutTier"] = "乱来"
        result = self.run_cli(value, self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("layoutTier must be one of", result.stdout)
        value = self.callback_v02()
        value["rows"][0]["layoutTier"] = "留白"
        result = self.run_cli(value, self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must equal the plan", result.stdout)

    def test_renderer_shows_bgm_basis_block_and_tier(self):
        callback_path = self.write("callback.json", self.callback_v02())
        plan_path = self.bgm_plan()
        alignment_path = self.alignment_artifact()
        output = self.root / "G3-回显卡-v0.2.md"
        result = subprocess.run([PYTHON, str(RENDERER), "--callback", str(callback_path), "--plan", str(plan_path),
                                 "--alignment", str(alignment_path), "--output", str(output)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        card = output.read_text(encoding="utf-8")
        self.assertIn("## BGM 依据区", card)
        self.assertIn("从音轨 01:00.000 起铺", card)
        self.assertIn("3/4", card)
        self.assertIn("phrase-01 · 推进档", card)


if __name__ == "__main__":
    unittest.main()
