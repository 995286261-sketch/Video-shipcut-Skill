import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skill" / "video-edit-plan"
INTAKE = ROOT / "skill" / "material-pack-intake" / "scripts" / "material_pack.py"
SCRIPT = SKILL / "scripts" / "g1_direction.py"
PYTHON = Path(sys.executable)


class G1DirectionTest(unittest.TestCase):
    def run_cli(self, *args):
        result = subprocess.run([str(PYTHON), str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")
        return result.returncode, json.loads(result.stdout)

    def create_pack(self, complete=True):
        temporary = tempfile.TemporaryDirectory()
        pack = Path(temporary.name) / "demo-pack"
        created = subprocess.run([str(PYTHON), str(INTAKE), "init", "--pack", str(pack)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, created.returncode)
        if complete:
            (pack / "01_需求说明.md").write_text("项目名：测试\n想讲什么：主题\n给谁看：观众\n目标时长：30 秒\n输出：横版 16:9\n希望的感觉：清晰\n不能说什么：无\n", encoding="utf-8")
            (pack / "04_授权说明.md").write_text("| 文件名 | 用途 | 是否可用于最终成片 | 来源或授权说明 |\n| --- | --- | --- | --- |\n| clip.mp4 | 测试 | 待确认 | 测试输入 |\n", encoding="utf-8")
            requirements = next(pack.glob("01_*.md"))
            with requirements.open("a", encoding="utf-8") as handle:
                handle.write("\nBGM decision: no_bgm\n")
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture")
            registered = subprocess.run([str(PYTHON), str(INTAKE), "register", "--pack", str(pack)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, registered.returncode)
        return temporary, pack

    def write_input(self, directory, value):
        value.setdefault("bgmDecision", "no_bgm")
        value.setdefault("directionChoice", {"id": "recommended-1", "label": "test direction", "source": "agent_recommendation"})
        if isinstance(value.get("outputPreferences"), dict):
            value["outputPreferences"].setdefault("usagePurpose", "brand_homepage")
        path = Path(directory) / "direction.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def valid_direction():
        return {"projectId": "demo-001", "coreQuestion": "要回答什么", "audience": "测试观众", "title": "编辑标题", "titleExpressionType": "editorial_expression", "coreViewpoint": "核心观点", "outputPreferences": {"aspectRatio": "16:9", "targetDurationSec": [60, 90]}, "styleRules": [], "expressionBoundaries": [], "claims": []}

    def test_incomplete_pack_blocks_before_g1(self):
        temporary, pack = self.create_pack(complete=False)
        with temporary:
            code, result = self.run_cli("check-pack", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertEqual("blocked", result["status"])

    def test_supported_claim_without_evidence_is_invalid(self):
        temporary, pack = self.create_pack()
        with temporary:
            direction = self.valid_direction()
            direction["claims"] = [{"claimId": "c1", "text": "一条事实", "status": "supported", "evidenceRefs": []}]
            input_path = self.write_input(temporary.name, direction)
            code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(input_path))
            self.assertEqual(2, code)
            self.assertEqual("invalid", result["status"])

    def test_supported_claim_with_pack_evidence_is_valid(self):
        temporary, pack = self.create_pack()
        with temporary:
            evidence = pack / "03_事实依据" / "fact.txt"
            evidence.write_text("可引用事实", encoding="utf-8")
            direction = self.valid_direction()
            direction["claims"] = [{"claimId": "c1", "text": "一条事实", "status": "supported", "evidenceRefs": [{"path": "03_事实依据/fact.txt", "locator": "第 1 行"}]}]
            input_path = self.write_input(temporary.name, direction)
            code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(input_path))
            self.assertEqual(0, code)
            self.assertEqual("valid", result["status"])

    def test_write_requires_explicit_confirmation(self):
        temporary, pack = self.create_pack()
        with temporary:
            input_path = self.write_input(temporary.name, self.valid_direction())
            workspace = Path(temporary.name) / "workspace"
            code, result = self.run_cli("write", "--pack", str(pack), "--workspace", str(workspace), "--input", str(input_path))
            self.assertEqual(2, code)
            self.assertEqual("blocked", result["status"])
            self.assertFalse((workspace / "创作方向").exists())

    def test_title_must_declare_expression_type(self):
        temporary, pack = self.create_pack()
        with temporary:
            direction = self.valid_direction()
            direction.pop("titleExpressionType")
            input_path = self.write_input(temporary.name, direction)
            code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(input_path))
            self.assertEqual(2, code)
            self.assertEqual("invalid", result["status"])

    def test_provided_bgm_requires_registered_g0_audio(self):
        temporary, pack = self.create_pack()
        with temporary:
            direction = self.valid_direction()
            direction["bgmDecision"] = "provided"
            input_path = self.write_input(temporary.name, direction)
            code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(input_path))
            self.assertEqual(2, code)
            self.assertEqual("invalid", result["status"])
            self.assertTrue(any(item["field"] == "bgmDecision" for item in result["errors"]))

    def test_missing_required_g1_fields_are_invalid(self):
        temporary, pack = self.create_pack()
        with temporary:
            for field in ("coreQuestion", "audience", "coreViewpoint", "outputPreferences", "styleRules", "expressionBoundaries"):
                direction = self.valid_direction()
                direction.pop(field)
                input_path = self.write_input(temporary.name, direction)
                code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(input_path))
                self.assertEqual(2, code, field)
                self.assertEqual("invalid", result["status"], field)

    def test_missing_style_or_boundary_never_reach_write(self):
        temporary, pack = self.create_pack()
        with temporary:
            workspace = Path(temporary.name) / "workspace"
            for field in ("styleRules", "expressionBoundaries"):
                direction = self.valid_direction()
                direction.pop(field)
                input_path = self.write_input(temporary.name, direction)
                code, result = self.run_cli("write", "--pack", str(pack), "--workspace", str(workspace), "--input", str(input_path), "--confirmed")
                self.assertEqual(2, code, field)
                self.assertEqual("invalid", result["status"], field)
            self.assertFalse((workspace / "创作方向").exists())

    def test_invalid_output_preferences_never_reach_write(self):
        temporary, pack = self.create_pack()
        with temporary:
            direction = self.valid_direction()
            direction["outputPreferences"] = []
            input_path = self.write_input(temporary.name, direction)
            workspace = Path(temporary.name) / "workspace"
            code, result = self.run_cli("write", "--pack", str(pack), "--workspace", str(workspace), "--input", str(input_path), "--confirmed")
            self.assertEqual(2, code)
            self.assertEqual("invalid", result["status"])
            self.assertFalse((workspace / "创作方向").exists())

    def test_missing_invalid_and_conflicting_project_id_never_overwrite(self):
        temporary, pack = self.create_pack()
        with temporary:
            workspace = Path(temporary.name) / "workspace"
            direction = self.valid_direction()
            direction.pop("projectId")
            invalid_input = self.write_input(temporary.name, direction)
            code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(invalid_input))
            self.assertEqual(2, code)
            self.assertEqual("invalid", result["status"])
            direction = self.valid_direction()
            direction["projectId"] = "../unsafe"
            invalid_input = self.write_input(temporary.name, direction)
            code, result = self.run_cli("validate", "--pack", str(pack), "--input", str(invalid_input))
            self.assertEqual(2, code)
            self.assertEqual("invalid", result["status"])
            input_path = self.write_input(temporary.name, self.valid_direction())
            first, _ = self.run_cli("write", "--pack", str(pack), "--workspace", str(workspace), "--input", str(input_path), "--confirmed")
            second, result = self.run_cli("write", "--pack", str(pack), "--workspace", str(workspace), "--input", str(input_path), "--confirmed")
            self.assertEqual(0, first)
            self.assertEqual(2, second)
            self.assertEqual("blocked", result["status"])

    def test_ui_only_promises_g1(self):
        yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("G1", yaml)
        self.assertNotIn("生成可追溯的本地视频剪辑计划", yaml)


if __name__ == "__main__":
    unittest.main()
