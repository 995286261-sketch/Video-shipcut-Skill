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

    def test_initialized_template_registers_when_machine_fields_are_filled(self):
        temporary, pack = self.create_pack()
        with temporary:
            requirements = pack / "01_需求说明.md"
            text = requirements.read_text(encoding="utf-8")
            replacements = {
                "想讲什么：": "想讲什么：测试主题",
                "给谁看：": "给谁看：测试观众",
                "目标时长：": "目标时长：30 秒",
                "输出：": "输出：横版 16:9",
                "希望的感觉：": "希望的感觉：清晰",
                "不能说什么：": "不能说什么：无",
            }
            for placeholder, value in replacements.items():
                self.assertIn(placeholder, text)
                text = text.replace(placeholder, value, 1)
            self.assertIn("\nBGM decision:\n", text)
            text = text.replace("\nBGM decision:\n", "\nBGM decision: no_bgm\n", 1)
            requirements.write_text(text, encoding="utf-8")
            (pack / "04_授权说明.md").write_text("""| 文件名 | 用途 | 是否可用于最终成片 | 来源或授权说明 |
| --- | --- | --- | --- |
| clip.mp4 | 测试 | 待确认 | 测试输入 |
""", encoding="utf-8")
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")

            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(0, code)
            self.assertEqual("completed", result["status"])

            code, result = self.run_cli("validate", "--pack", str(pack))
            self.assertEqual(0, code)
            self.assertEqual("complete", result["status"])

    def test_invalid_bgm_decision_is_rejected(self):
        temporary, pack = self.create_pack()
        with temporary:
            self.fill_required_documents(pack)
            with next(pack.glob("01_*.md")).open("a", encoding="utf-8") as handle:
                handle.write("\nBGM decision: choose_later\n")
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertEqual("incomplete", result["status"])
            self.assertTrue(any("BGM decision" in item for item in result["incompleteRequiredEntries"]))

    def test_register_blocks_stream_encrypted_fake_audio(self):
        """Issue 023: NetEase-style encrypted cache renamed to .mp3 must block registration."""
        temporary, pack = self.create_pack()
        with temporary:
            self.fill_required_documents(pack)
            with next(pack.glob("01_*.md")).open("a", encoding="utf-8") as handle:
                handle.write("\nBGM decision: provided\n")
            (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")
            (pack / "07_授权音频" / "Interlinked.mp3").write_bytes(b"CTENFDAM" + b"\x00" * 4096)
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertEqual("blocked", result["status"])
            self.assertEqual("audio_decode_probe_failed", result["blockers"][0]["type"])
            self.assertEqual(1, len(result["undecodableAudio"]))
            self.assertIn("Interlinked.mp3", result["undecodableAudio"][0]["relativePath"])
            self.assertFalse((pack / "material-pack.json").exists(), "blocked register must not write the manifest")

    @staticmethod
    def audio_sha256(path):
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()

    def write_bgm_registration(self, pack, audio_path, **overrides):
        import hashlib
        record = {"schemaVersion": "0.1", "skill": "music-expert", "provenance": "manual_registration",
                  "title": audio_path.stem, "sha256": self.audio_sha256(audio_path),
                  "license": "cc0", "licenseEvidence": "https://example.org/cc0",
                  "distributionBoundary": "internal_test",
                  "decodeProbe": {"status": "passed", "engine": "ffmpeg"}}
        record.update(overrides)
        doc = pack / "07_授权音频" / f"BGM-候选登记-{audio_path.stem}-REG.json"
        doc.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return doc

    def write_bgm_analysis(self, pack, audio_path):
        report = {"schemaVersion": "0.1", "skill": "music-expert", "purpose": "bgm_music_analysis",
                  "source": {"sha256": self.audio_sha256(audio_path), "decodedDurationMs": 200},
                  "tempoBpm": 120.0, "energySegments": [], "hitPoints": []}
        doc = pack / "07_授权音频" / f"BGM-分析报告-{audio_path.stem}-ANA.json"
        doc.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return doc

    def make_provided_bgm_pack(self, pack):
        import shutil
        import subprocess
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is required to synthesize a decodable wav")
        self.fill_required_documents(pack)
        with next(pack.glob("01_*.md")).open("a", encoding="utf-8") as handle:
            handle.write("\nBGM decision: provided\n")
        (pack / "02_原始素材" / "clip.mp4").write_bytes(b"fixture-media")
        audio = pack / "07_授权音频" / "real.wav"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", str(audio)],
                       check=True, capture_output=True)
        return audio

    def test_register_records_decode_probe_for_real_audio(self):
        temporary, pack = self.create_pack()
        with temporary:
            audio = self.make_provided_bgm_pack(pack)
            self.write_bgm_registration(pack, audio)
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(0, code, result)
            self.assertEqual("completed", result["status"])
            manifest = json.loads((pack / "material-pack.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", manifest["audioAssets"][0]["decodeProbe"]["status"])
            self.assertIn("bgmAnalysisPending", result)  # registration present, analysis absent -> soft prompt

    def test_provided_audio_without_registration_is_incomplete(self):
        """N1: decodable bytes alone are not a license chain."""
        temporary, pack = self.create_pack()
        with temporary:
            self.make_provided_bgm_pack(pack)
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(2, code)
            self.assertEqual("incomplete", result["status"])
            self.assertEqual(["07_授权音频/real.wav"], [p for p in result["unregisteredAudio"]])
            self.assertTrue(any("music-expert" in item for item in result["incompleteRequiredEntries"]))
            self.assertFalse((pack / "material-pack.json").exists())

    def test_registration_and_analysis_are_hashed_into_manifest(self):
        import hashlib
        temporary, pack = self.create_pack()
        with temporary:
            audio = self.make_provided_bgm_pack(pack)
            registration = self.write_bgm_registration(pack, audio, styleTags=["epic"])
            analysis = self.write_bgm_analysis(pack, audio)
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(0, code, result)
            self.assertNotIn("bgmAnalysisPending", result)
            asset = json.loads((pack / "material-pack.json").read_text(encoding="utf-8"))["audioAssets"][0]
            self.assertEqual(hashlib.sha256(registration.read_bytes()).hexdigest().upper(), asset["bgmRegistration"]["sha256"])
            self.assertEqual("cc0", asset["bgmRegistration"]["licenseType"])
            self.assertEqual(hashlib.sha256(analysis.read_bytes()).hexdigest().upper(), asset["bgmAnalysis"]["sha256"])

    def test_validate_detects_tampered_bgm_registration(self):
        temporary, pack = self.create_pack()
        with temporary:
            audio = self.make_provided_bgm_pack(pack)
            registration = self.write_bgm_registration(pack, audio)
            code, result = self.run_cli("register", "--pack", str(pack))
            self.assertEqual(0, code, result)
            tampered = json.loads(registration.read_text(encoding="utf-8"))
            tampered["license"] = "owned"  # someone edits the license after registration
            registration.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
            code, result = self.run_cli("validate", "--pack", str(pack))
            self.assertEqual(1, len([f for f in result["manifestFailures"] if f["type"] == "bgmRegistration_tampered"]))

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
