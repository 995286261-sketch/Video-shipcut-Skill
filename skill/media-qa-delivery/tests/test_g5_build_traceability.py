"""g5_build_traceability 负例优先（banshee-001 台账⑪甲案：机械生成唯一正道）。

进程内直调 main（importlib 先例，01c320a 同型）：不起子进程、argv 不经 shell。
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "skill" / "media-qa-delivery" / "scripts" / "g5_build_traceability.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("g5_build_traceability", BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder()


class TraceabilityFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = "fixture-trace"
        self.assets = {
            "asset-a": ("02_原始素材/a.mp4", "A" * 64),
            "asset-b": ("02_原始素材/b.mp4", "B" * 64),
        }
        self.json("material-pack.json", {
            "schemaVersion": "0.1", "materialPackId": "pack-1",
            "sourceAssets": [{"assetId": key, "relativePath": path, "sha256": sha}
                             for key, (path, sha) in self.assets.items()],
            "audioAssets": [],
        })
        self.timeline = 12_000
        self.segments = [
            {"segmentId": "s0", "assetId": "asset-a", "startMs": 0, "endMs": 4_000,
             "outputStartMs": 0, "outputEndMs": 4_000},
            {"segmentId": "s1", "assetId": "asset-b", "startMs": 10_000, "endMs": 14_000,
             "outputStartMs": 4_000, "outputEndMs": 8_000},
            {"segmentId": "s2", "assetId": "asset-a", "startMs": 20_000, "endMs": 24_000,
             "outputStartMs": 8_000, "outputEndMs": 12_000},
        ]
        self.write_plan()
        self.write_assembly()
        self.json("chapters.json", {"chapters": [
            {"chapterId": "ch-01", "outputStartMs": 0, "outputEndMs": 4_000},
            {"chapterId": "ch-02", "outputStartMs": 4_000, "outputEndMs": 8_000},
            {"chapterId": "ch-03", "outputStartMs": 8_000, "outputEndMs": 12_000}]})

    def write_plan(self, **overrides):
        plan = {"schemaVersion": "0.1", "projectId": self.project, "node": "G3",
                "status": "approved_for_g4", "timelineDurationMs": self.timeline,
                "segments": self.segments}
        plan.update(overrides)
        self.json("plan.json", plan)

    def write_assembly(self, **overrides):
        assembly = {"schemaVersion": "0.1", "node": "G4", "projectId": self.project,
                    "timelineDurationMs": self.timeline,
                    "segments": [{"segmentId": seg["segmentId"], "file": f"{seg['segmentId']}.mp4",
                                  "sha256": "F" * 64} for seg in self.segments]}
        assembly.update(overrides)
        self.json("assembly.json", assembly)

    def json(self, name, value):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return self.root / name

    def run_build(self, output=None):
        target = output if output is not None else self.root / "bundle" / "source-timecode-list.json"
        pairs = (("plan", self.root / "plan.json"), ("assembly-record", self.root / "assembly.json"),
                 ("material-pack", self.root / "material-pack.json"), ("chapters", self.root / "chapters.json"),
                 ("output", target))
        argv = [token for flag, value in pairs for token in ("--" + flag, str(value))]
        buffer = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(buffer):
            try:
                BUILDER.main(argv)
            except SystemExit as exit_error:
                code = int(exit_error.code or 0)
        payload = {}
        for line in buffer.getvalue().splitlines():
            line = line.strip()
            if line.startswith("{"):
                payload = json.loads(line)
                break
        return code, payload, target


class BuildHappyPathTests(TraceabilityFixture, unittest.TestCase):
    def test_projects_plan_grid_verbatim_and_derives_chapters(self):
        code, payload, target = self.run_build()
        self.assertEqual(0, code, payload)
        self.assertEqual("written", payload["status"])
        trace = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(self.project, trace["projectId"])
        self.assertIn("g5_build_traceability", trace["generatedBy"])
        self.assertEqual(len(self.segments), len(trace["segments"]))
        seg0 = trace["segments"][0]
        self.assertEqual(self.assets["asset-a"][0], seg0["sourceAssetPath"])
        self.assertEqual("A" * 64, seg0["sourceSha256"])
        self.assertEqual({"s0"}, set(trace["chapters"][0]["segments"]))
        self.assertEqual("clips/ch-01.mp4", trace["chapters"][0]["output"])
        # 绑定行：输入件 path+大写 sha（R2 同型漂移可追）
        for key in ("plan", "assemblyRecord", "materialPack"):
            binding = trace["bindings"][key]
            self.assertEqual(64, len(binding["sha256"]))
            self.assertEqual(binding["sha256"], binding["sha256"].upper())

    def test_membership_follows_output_grid_not_order(self):
        # 章节声明顺序打乱：成员按输出区间落入判定，而非数组顺序
        self.json("chapters.json", {"chapters": [
            {"chapterId": "ch-01", "outputStartMs": 0, "outputEndMs": 4_000},
            {"chapterId": "ch-03", "outputStartMs": 4_000, "outputEndMs": 8_000},
            {"chapterId": "ch-02", "outputStartMs": 8_000, "outputEndMs": 12_000}]})
        code, payload, target = self.run_build()
        self.assertEqual(0, code, payload)
        trace = json.loads(target.read_text(encoding="utf-8"))
        by_id = {c["chapterId"]: c["segments"] for c in trace["chapters"]}
        self.assertEqual(["s1"], by_id["ch-03"])
        self.assertEqual(["s2"], by_id["ch-02"])


class BuildNegativeTests(TraceabilityFixture, unittest.TestCase):
    def test_refuses_overwrite_same_version(self):
        code, _, target = self.run_build()
        self.assertEqual(0, code)
        code, payload, _ = self.run_build(target)
        self.assertEqual(2, code)
        self.assertIn("拒绝覆盖", payload["errors"][0])

    def test_assembly_plan_version_mismatch_strikes(self):
        self.write_assembly(timelineDurationMs=9_000)
        code, payload, _ = self.run_build()
        self.assertEqual(2, code)
        self.assertTrue(any("不同版" in err or "timelineDurationMs" in err for err in payload["errors"]))

    def test_unregistered_asset_strikes_by_name(self):
        self.write_plan(segments=[dict(self.segments[0], assetId="asset-ghost")])
        code, payload, _ = self.run_build()
        self.assertEqual(2, code)
        self.assertTrue(any("素材包登记" in err for err in payload["errors"]))

    def test_unapproved_plan_strikes(self):
        self.write_plan(status="draft")
        code, payload, _ = self.run_build()
        self.assertEqual(2, code)
        self.assertTrue(any("未批准" in err for err in payload["errors"]))

    def test_chapter_gap_strikes(self):
        self.json("chapters.json", {"chapters": [
            {"chapterId": "ch-01", "outputStartMs": 0, "outputEndMs": 4_000},
            {"chapterId": "ch-02", "outputStartMs": 5_000, "outputEndMs": 8_000},
            {"chapterId": "ch-03", "outputStartMs": 8_000, "outputEndMs": 12_000}]})
        code, payload, _ = self.run_build()
        self.assertEqual(2, code)
        self.assertTrue(any("连续铺满" in err for err in payload["errors"]))

    def test_chapter_count_below_three_strikes(self):
        self.json("chapters.json", {"chapters": [
            {"chapterId": "ch-01", "outputStartMs": 0, "outputEndMs": 8_000},
            {"chapterId": "ch-02", "outputStartMs": 8_000, "outputEndMs": 12_000}]})
        code, payload, _ = self.run_build()
        self.assertEqual(2, code)
        self.assertTrue(any("3–5" in err for err in payload["errors"]))

    def test_orphan_segment_strikes(self):
        # 窗口铺满，但一段跨两窗边界=没有任何窗口完整容纳它→孤儿罢工点名
        self.write_plan(segments=[
            dict(self.segments[0], outputEndMs=4_000),
            dict(self.segments[1], outputStartMs=4_000, outputEndMs=8_000),
            {"segmentId": "s2", "assetId": "asset-a", "startMs": 20_000, "endMs": 24_000,
             "outputStartMs": 7_000, "outputEndMs": 12_000},
        ])
        code, payload, _ = self.run_build()
        self.assertEqual(2, code)
        self.assertTrue(any("不属于任何章节" in err for err in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
