"""In-process tests for subtitle_experience.py（唯一写入口 + 三条红线）."""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/subtitle-expert/scripts/subtitle_experience.py"
_spec = importlib.util.spec_from_file_location("subtitle_experience", SCRIPT)
lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lib)


class SubtitleExperienceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / "library"

    def run_cli(self, *argv):
        buffer = io.StringIO()
        saved = sys.argv
        sys.argv = ["subtitle_experience", "--library", str(self.library), *map(str, argv)]
        try:
            with contextlib.redirect_stdout(buffer):
                try:
                    code = lib.main()
                except SystemExit as error:
                    code = error.code if isinstance(error.code, int) else 2
        finally:
            sys.argv = saved
        output = buffer.getvalue().strip().splitlines()
        payload = json.loads(output[-1]) if output else {}
        return code, payload

    def write(self, name, value):
        path = self.root / name
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path

    def font(self, name="PingFangSC.ttf"):
        return self.write(name, b"\x00\x01fake-font-bytes")

    def contract(self, **lane_extra):
        lane = {"fontsize": 64, "maxLines": 2, "topPct": 70, "bottomPct": 84}
        lane.update(lane_extra)
        return self.write("layout.json", json.dumps({
            "schemaVersion": "0.1", "node": "G3", "projectId": "demo-001",
            "resolution": [1920, 1080], "lanes": {"narration": lane}}, ensure_ascii=False))

    # ---- 红线 3：未验证的不写 ----

    def test_usable_font_without_evidence_is_refused(self):
        code, payload = self.run_cli("record-font", "--font-file", self.font(),
                                     "--usage", "libass", "--verdict", "usable")
        self.assertEqual(2, code)
        self.assertIn("--evidence", payload["error"])

    def test_unknown_font_file_is_refused(self):
        code, payload = self.run_cli("record-font", "--font-file", self.root / "absent.ttf",
                                     "--usage", "libass", "--verdict", "blocked")
        self.assertEqual(2, code)

    def test_font_identity_is_file_sha_and_history_append_only(self):
        font = self.font()
        code, first = self.run_cli("record-font", "--font-file", font, "--usage", "drawtext",
                                   "--verdict", "rejected", "--evidence", "㉛ 首-face 缺简体（002 活测）")
        self.assertEqual(0, code)
        code, second = self.run_cli("record-font", "--font-file", font, "--usage", "libass",
                                    "--verdict", "usable", "--evidence", "zaku/tiger/002 交付成片目视无缺字")
        self.assertEqual(0, code)
        self.assertEqual(first["file"], second["file"])
        record = json.loads(Path(first["file"]).read_text(encoding="utf-8"))
        self.assertEqual(2, len(record["records"]))          # 只增不删
        self.assertIn("sha256", record)                       # 身份=文件哈希

    def test_family_record_needs_libass_and_evidence(self):
        # 09-21 实测事实：本机无 PingFang.ttc 文件，libass 按 family 经系统字体服务解析——
        # family 档案身份=family 名，只许 libass 路线，usable 同样必须带真实交付证据。
        code, payload = self.run_cli("record-font", "--font-family", "PingFang SC",
                                     "--usage", "libass", "--verdict", "usable")
        self.assertEqual(2, code)
        self.assertIn("--evidence", payload["error"])
        code, result = self.run_cli("record-font", "--font-family", "PingFang SC", "--usage", "libass",
                                    "--verdict", "usable", "--evidence", "zaku/002/tiger 交付成片目视无缺字")
        self.assertEqual(0, code)
        record = json.loads(Path(result["file"]).read_text(encoding="utf-8"))
        self.assertEqual("family", record["identity"])
        self.assertNotIn("sha256", record)
        code, payload = self.run_cli("record-font", "--font-family", "Songti SC",
                                     "--usage", "drawtext", "--verdict", "blocked")
        self.assertEqual(2, code)      # drawtext 必须指到具体文件

    # ---- 红线 1：库=建议层，没门禁批准不入库 ----

    def test_layout_without_gate_approval_is_refused(self):
        code, payload = self.run_cli("record-layout", "--contract", self.contract(),
                                     "--approval", self.root / "nope.md")
        self.assertEqual(2, code)
        self.assertIn("门禁", payload["error"])

    # ---- 红线 2：呈现层白名单，时刻/文本进不去 ----

    def test_layout_records_only_narration_presentation_fields(self):
        contract = self.contract(cueStartsMs=[0, 5000], text="宇宙世纪", Style="Narration")
        approval = self.write("approve.md", "确认 G3\n")
        code, result = self.run_cli("record-layout", "--contract", contract, "--approval", approval)
        self.assertEqual(0, code)
        record = json.loads(Path(result["file"]).read_text(encoding="utf-8"))
        self.assertEqual({"fontsize", "maxLines", "topPct", "bottomPct"}, set(record["narration"]))
        blob = json.dumps(record, ensure_ascii=False)
        self.assertNotIn("宇宙世纪", blob)
        self.assertNotIn("cueStartsMs", blob)

    def test_layout_same_family_appends_projects(self):
        approval = self.write("approve.md", "确认 G3\n")
        self.run_cli("record-layout", "--contract", self.contract(), "--approval", approval)
        other = self.write("layout2.json", json.dumps({"schemaVersion": "0.1", "node": "G3",
                        "projectId": "demo-002", "resolution": [1920, 1080],
                        "lanes": {"narration": {"fontsize": 64, "maxLines": 2}}}))
        code, result = self.run_cli("record-layout", "--contract", other, "--approval", approval)
        record = json.loads(Path(result["file"]).read_text(encoding="utf-8"))
        self.assertEqual(["demo-001", "demo-002"], record["projects"])

    # ---- renderer：只存探测派生事实 ----

    def test_renderer_record_requires_real_profile(self):
        fake = self.write("fake.json", json.dumps({"purpose": "something_else"}))
        code, payload = self.run_cli("record-renderer", "--profile", fake)
        self.assertEqual(2, code)
        profile = self.write("cap.json", json.dumps({
            "schemaVersion": "0.1", "skill": "subtitle-expert", "purpose": "subtitle_renderer_profile",
            "host": {"system": "Darwin", "release": "25", "machine": "arm64"},
            "ffmpeg": {"libass": "unknown"}, "autoWrap": {"value": False, "evidence": None, "basis": "conservative"}}))
        code, result = self.run_cli("record-renderer", "--profile", profile)
        self.assertEqual(0, code)

    def test_query_carries_disclaimer_and_filters(self):
        approval = self.write("approve.md", "确认 G3\n")
        self.run_cli("record-layout", "--contract", self.contract(), "--approval", approval)
        code, payload = self.run_cli("query", "--kind", "layout", "--resolution", "1920x1080")
        self.assertEqual(0, code)
        self.assertEqual(1, payload["count"])
        self.assertFalse(payload["resolutionMiss"])  # 精确命中不走 fallback（防假阳性）
        self.assertIn("推荐≠批准", payload["disclaimer"])
        code, payload = self.run_cli("query", "--kind", "layout", "--resolution", "1080x1920")
        self.assertTrue(payload["resolutionMiss"])   # 无精确档：如实 miss 并给近邻参照，绝不假命中
        self.assertEqual(1, payload["count"])


if __name__ == "__main__":
    unittest.main()
