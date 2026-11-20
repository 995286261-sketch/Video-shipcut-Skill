"""㉙（mickey-001 真案）：遮罩合同唯一机械生成入口=g4_build_mask_contract.py。
对账矩阵：无观察拒 / 缺 captionZones 拒 / 带顶按观测抬升覆盖歌词行 / mode=none 矛盾拒 /
拒覆盖 / derivedFrom 指纹绑定 / 未批准计划拒 / 参数白名单。
形制说明：本文件走进程内直调 main()（argparse 校验+对账罢工+落盘全链同样覆盖）。
纪律上这些合同脚本的对外契约=罢工必 nonzero+结构化 error，由 __main__ 包装层保证；
该包装层在 g4 家族逐字同形（g4_prepare 已有 subprocess 形制用例），此处不重复。"""
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
BUILDER_PATH = ROOT / "skill" / "local-video-render" / "scripts" / "g4_build_mask_contract.py"
_spec = importlib.util.spec_from_file_location("g4_build_mask_contract", BUILDER_PATH)
BUILDER = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BUILDER)


class MaskContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "G4-遮罩合同-v0.1.json"
        self.plan_path = self.root / "plan.json"
        self.ledger_path = self.root / "ledger.json"
        self.margin = "2"
        self.color = "black@0.85"

    def segment(self, mode="mask"):
        return {"segmentId": "s8", "assetId": "clip-B", "startMs": 73_410, "endMs": 83_551,
                "outputStartMs": 56_500, "outputEndMs": 66_600,
                "sourceCaptionTreatment": {"mode": mode}}

    def write_plan(self, status="approved_for_g4", mode="mask"):
        value = {"schemaVersion": "0.1", "projectId": "mickey-test", "status": status,
                 "segments": [self.segment(mode)]}
        self.plan_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def burned_record(self, record_id="obs-B14", with_zones=True):
        record = {"recordId": record_id, "sourceAssetId": "clip-B", "sourceSha256": "x",
                  "sourceMs": 78_000, "analysisStatus": "completed", "riskFlags": ["burned_subtitle"],
                  "observedVisuals": "画面下方两行卡拉OK歌词"}
        if with_zones:
            record["captionZones"] = [
                {"text": "(Mickey)", "line": 1, "kind": "lyrics", "yPctRange": [81, 86]},
                {"text": "(Mouse)", "line": 2, "kind": "lyrics", "yPctRange": [88, 93]}]
        return record

    def write_ledger(self, records):
        by_id = {record["recordId"]: record for record in records}
        for record in records:
            if record.get("supersedesRecordId") in by_id:
                by_id[record["supersedesRecordId"]]["analysisStatus"] = "superseded"
                by_id[record["supersedesRecordId"]]["supersededBy"] = record["recordId"]
        value = {"schemaVersion": "0.1", "node": "G3", "projectId": "mickey-test", "records": records}
        self.ledger_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def invoke(self):
        argv = [str(BUILDER_PATH), "--plan", str(self.plan_path), "--ledger", str(self.ledger_path),
                "--width", "1280", "--height", "720", "--output", str(self.output),
                "--margin-pct", self.margin, "--color", self.color]
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            BUILDER.main()
        return json.loads(stdout.getvalue())

    def contract(self):
        return json.loads(self.output.read_text(encoding="utf-8"))

    def test_contract_band_top_raised_to_cover_observed_lyrics(self):
        # 观测最低下沿 81%，margin 2 → 带顶 79% → 720p 下 569px；y1=画布底缘（㉚ 如实）
        self.write_plan()
        self.write_ledger([self.burned_record()])
        value = self.invoke()
        self.assertEqual("written", value["status"])
        mask = self.contract()["masks"][0]
        self.assertEqual([569, 720], mask["bandYpx"])
        self.assertLess(mask["bandYpx"][0], round(720 * 0.81))  # 必须盖住歌词首行
        self.assertEqual("m-s8", mask["maskId"])
        self.assertEqual([56_500, 66_600], [mask["outputFromMs"], mask["outputToMs"]])
        self.assertIn("obs-B14", mask["basis"])
        contract = self.contract()
        self.assertIn("㉙", contract["generatedBy"])
        derived = contract["derivedFrom"]
        self.assertEqual(hashlib.sha256(self.plan_path.read_bytes()).hexdigest().upper(),
                         derived["planSha256"])
        self.assertEqual(hashlib.sha256(self.ledger_path.read_bytes()).hexdigest().upper(),
                         derived["ledgerSha256"])

    def test_mask_without_any_observation_refuses(self):
        self.write_plan()
        self.write_ledger([])
        with self.assertRaisesRegex(ValueError, "遮罩无证据"):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_burned_record_missing_zones_names_record_and_refuses(self):
        self.write_plan()
        self.write_ledger([self.burned_record(with_zones=False)])
        with self.assertRaisesRegex(ValueError, "obs-B14") as caught:
            self.invoke()
        self.assertIn("captionZones", str(caught.exception))

    def test_superseded_observation_does_not_justify_mask(self):
        original = self.burned_record("obs-old")
        replacement = self.burned_record("obs-new")
        replacement["supersedesRecordId"] = "obs-old"
        replacement["riskFlags"] = []  # 改判后无烧字
        replacement.pop("captionZones")
        self.write_plan()
        self.write_ledger([original, replacement])
        with self.assertRaisesRegex(ValueError, "遮罩无证据"):
            self.invoke()

    def test_mode_none_contradicting_burned_observation_refuses(self):
        self.write_plan(mode="none")
        self.write_ledger([self.burned_record()])
        with self.assertRaises(ValueError) as caught:
            self.invoke()
        self.assertIn("矛盾", str(caught.exception))
        self.assertIn("obs-B14", str(caught.exception))

    def test_mode_none_without_burned_writes_empty_contract(self):
        self.write_plan(mode="none")
        self.write_ledger([])
        self.assertEqual("written", self.invoke()["status"])
        self.assertEqual([], self.contract()["masks"])

    def test_rerun_refuses_overwrite(self):
        self.write_plan()
        self.write_ledger([self.burned_record()])
        self.invoke()
        with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
            self.invoke()

    def test_unapproved_plan_refuses(self):
        self.write_plan(status="review_required")
        self.write_ledger([self.burned_record()])
        with self.assertRaisesRegex(ValueError, "未批准"):
            self.invoke()

    def test_margin_and_color_whitelist(self):
        self.write_plan()
        self.write_ledger([self.burned_record()])
        self.margin = "60"
        with self.assertRaisesRegex(ValueError, "margin-pct"):
            self.invoke()
        self.margin = "2"
        self.color = "black@0.85" + " spaced"
        with self.assertRaisesRegex(ValueError, "color"):
            self.invoke()

    def test_observation_outside_source_window_not_counted(self):
        record = self.burned_record()
        record["sourceMs"] = 10_000
        self.write_plan()
        self.write_ledger([record])
        with self.assertRaisesRegex(ValueError, "遮罩无证据"):
            self.invoke()


if __name__ == "__main__":
    unittest.main()
