import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
SCRIPT = SKILL / "scripts" / "material_pack.py"


class MaterialPackTest(unittest.TestCase):
    def run_cli(self, *args):
        result = subprocess.run([str(PYTHON), str(SCRIPT), *args], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def create_pack(self):
        temporary = tempfile.TemporaryDirectory()
        pack = Path(temporary.name) / "demo-pack"
        code, created = self.run_cli("init", "--pack", str(pack))
        self.assertEqual(0, code)
        self.assertEqual("created", created["status"])
        return temporary, pack

    @staticmethod
    def fill_required_documents(pack):
        (pack / "01_需求说明.md").write_text("""项目名：测试\n想讲什么：测试主题\n给谁看：测试观众\n目标时长：30 秒\n输出：横版 16:9\n希望的感觉：清晰\n不能说什么：无\n""", encoding="utf-8")
        (pack / "04_授权说明.md").write_text("""| 文件名 | 用途 | 是否可用于最终成片 | 来源或授权说明 |\n| --- | --- | --- | --- |\n| clip.mp4 | 测试 | 待确认 | 测试输入 |\n""", encoding="utf-8")

    def register_complete_pack(self, pack):
        self.fill_required_documents(pack)
        with next(pack.glob("01_*.md")).open("a", encoding="utf-8") as handle:
            handle.write("\nBGM decision: no_bgm\n")
        (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")
        code, result = self.run_cli("register", "--pack", str(pack))
        self.assertEqual(0, code)
        self.assertEqual("completed", result["status"])

    def test_template_placeholders_are_incomplete(self):
        temporary, pack = self.create_pack()
        with temporary:
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertEqual("incomplete", result["status"])
            self.assertIn("01_需求说明.md", result["emptyRequiredEntries"])
            self.assertIn("04_授权说明.md", result["emptyRequiredEntries"])

    def test_bgm_decision_is_required(self):
        temporary, pack = self.create_pack()
        with temporary:
            self.fill_required_documents(pack)
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertTrue(any("BGM decision" in item for item in result["incompleteRequiredEntries"]))

    def test_duplicate_file_names_get_unique_asset_ids(self):
        temporary, pack = self.create_pack()
        with temporary:
            self.fill_required_documents(pack)
            with next(pack.glob("01_*.md")).open("a", encoding="utf-8") as handle:
                handle.write("\nBGM decision: no_bgm\n")
            for folder in ("a", "b"):
                target = pack / "02_原始素材" / folder
                target.mkdir()
                (target / "clip.mp4").write_bytes(folder.encode("ascii"))
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(0, code)
            manifest = json.loads((pack / "material-pack.json").read_text(encoding="utf-8"))
            ids = [asset["assetId"] for asset in manifest["sourceAssets"]]
            self.assertEqual(2, result["sourceAssetCount"])
            self.assertEqual(len(ids), len(set(ids)))

    def test_validate_accepts_utf8_bom_manifest(self):
        temporary, pack = self.create_pack()
        with temporary:
            self.register_complete_pack(pack)
            manifest = pack / "material-pack.json"
            manifest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8-sig")
            code, result = self.run_cli("validate", "--pack", str(pack))
            self.assertEqual(0, code)
            self.assertEqual("complete", result["status"])

    def test_validate_detects_hash_mismatch(self):
        temporary, pack = self.create_pack()
        with temporary:
            self.register_complete_pack(pack)
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"changed")
            code, result = self.run_cli("validate", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertIn("sha256_mismatch", [item["type"] for item in result["manifestFailures"]])

    def test_validate_rejects_escaping_manifest_path(self):
        temporary, pack = self.create_pack()
        with temporary:
            self.register_complete_pack(pack)
            manifest_path = pack / "material-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sourceAssets"][0]["relativePath"] = "../outside.mp4"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            code, result = self.run_cli("validate", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertIn("missing_or_escaping_path", [item["type"] for item in result["manifestFailures"]])


if __name__ == "__main__":
    unittest.main()
