import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_g3_callback.py"
PYTHON = sys.executable


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
                "narrationText": "口播原文", "sourceStartMs": start + 10000, "sourceEndMs": start + 11000,
                "observedVisuals": "实际可见的目标主体", "semanticStatus": "direct_match", "subjectStatus": "target_confirmed",
                "riskSummary": "左上角水印需裁切", "bgmPhrase": "phrase-01", "transitionInstruction": "硬切"})
        return {"schemaVersion": "0.1", "node": "G3", "projectId": "p", "callbackType": "final_review",
            "durationMs": 2000, "columns": ["片段 ID", "输出时间", "对应口播", "源片区间", "用途 / 实际画面观察", "语义匹配 / 主体状态 / 风险", "BGM 乐句", "转场指令"], "rows": rows}

    def run_cli(self, callback, plan=None):
        callback_path = self.write("callback.json", callback)
        command = [PYTHON, str(SCRIPT), "--callback", str(callback_path)]
        if plan:
            command += ["--plan", str(plan)]
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8")

    def test_valid_final_callback_passes(self):
        result = self.run_cli(self.callback(), self.plan())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_output_time_field_is_blocked(self):
        value = self.callback()
        del value["rows"][0]["outputStartMs"]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outputStartMs", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
