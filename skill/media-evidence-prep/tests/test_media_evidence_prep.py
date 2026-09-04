import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
WRITE = SKILL / "scripts" / "write_transcript_artifacts.py"
TRANSCRIBE = SKILL / "scripts" / "local_transcribe.py"
PYTHON = Path(sys.executable)


def run_script(script, *args):
    result = subprocess.run([str(PYTHON), str(script), *args], capture_output=True, text=True, encoding="utf-8")
    return result.returncode, json.loads(result.stdout)


def valid_segment(start_ms=0, end_ms=1000, text="测试", segment_id="tr-0001"):
    return {"segmentId": segment_id, "startMs": start_ms, "endMs": end_ms, "text": text}


class WriteTranscriptArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_input(self, segments):
        path = self.root / "transcript.json"
        path.write_text(json.dumps({"schemaVersion": "0.1", "segments": segments}, ensure_ascii=False), encoding="utf-8")
        return path

    def run_write(self, input_path, output_dir=None, source_pack=None):
        output_dir = output_dir or self.root / "out"
        args = ["--input", str(input_path), "--output-dir", str(output_dir)]
        if source_pack is not None:
            args += ["--source-pack", str(source_pack)]
        return run_script(WRITE, *args), output_dir

    def test_valid_transcript_generates_artifacts(self):
        input_path = self.write_input([valid_segment(), valid_segment(start_ms=1000, end_ms=2000, segment_id="tr-0002")])
        (code, result), output_dir = self.run_write(input_path)
        self.assertEqual(0, code)
        self.assertEqual("completed", result["status"])
        self.assertTrue((output_dir / "transcript.srt").is_file())
        self.assertTrue((output_dir / "transcript.txt").is_file())
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["validation"]["passed"])
        self.assertEqual(2, manifest["segments"])

    def test_boolean_timestamp_rejected(self):
        input_path = self.write_input([{"segmentId": "tr-0001", "startMs": True, "endMs": 2000, "text": "test"}])
        (code, result), _ = self.run_write(input_path)
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_negative_timestamp_rejected(self):
        input_path = self.write_input([valid_segment(start_ms=-1, end_ms=100)])
        (code, result), _ = self.run_write(input_path)
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_non_string_text_rejected(self):
        input_path = self.write_input([{"segmentId": "tr-0001", "startMs": 0, "endMs": 1000, "text": 12345}])
        (code, result), _ = self.run_write(input_path)
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_missing_segment_id_rejected(self):
        input_path = self.write_input([{"startMs": 0, "endMs": 1000, "text": "无ID"}])
        (code, result), _ = self.run_write(input_path)
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_duplicate_segment_id_rejected(self):
        input_path = self.write_input([valid_segment(), valid_segment(start_ms=1000, end_ms=2000, segment_id="tr-0001")])
        (code, result), _ = self.run_write(input_path)
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_missing_input_file_reports_json(self):
        (code, result), _ = self.run_write(self.root / "missing.json")
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_output_inside_material_pack_blocked(self):
        pack = self.root / "material-pack"
        pack.mkdir()
        input_path = self.write_input([valid_segment()])
        inside = pack / "02_原始素材"
        (code, result), _ = self.run_write(input_path, output_dir=inside, source_pack=pack)
        self.assertEqual(2, code)
        self.assertEqual("blocked", result["status"])
        self.assertEqual("output_inside_material_pack", result["blockers"][0]["type"])

    def test_output_outside_material_pack_allowed(self):
        pack = self.root / "material-pack"
        pack.mkdir()
        input_path = self.write_input([valid_segment()])
        (code, result), output_dir = self.run_write(input_path, source_pack=pack)
        self.assertEqual(0, code)
        self.assertEqual("completed", result["status"])
        self.assertTrue((output_dir / "transcript.srt").is_file())


class LocalTranscribeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model_dir = self.root / "models"
        self.model_dir.mkdir()

    def run_transcribe(self, input_path, source_pack=None):
        output = self.root / "out" / "transcript.json"
        args = ["--input", str(input_path), "--output", str(output), "--model-dir", str(self.model_dir)]
        if source_pack is not None:
            args += ["--source-pack", str(source_pack)]
        return run_script(TRANSCRIBE, *args), output

    def test_missing_input_reports_json(self):
        (code, result), _ = self.run_transcribe(self.root / "missing.mp4")
        self.assertEqual(2, code)
        self.assertEqual("invalid", result["status"])

    def test_missing_model_dir_blocked(self):
        media = self.root / "clip.mp4"
        media.write_bytes(b"fixture")
        result = subprocess.run(
            [str(PYTHON), str(TRANSCRIBE), "--input", str(media), "--output", str(self.root / "out.json"), "--model-dir", str(self.root / "nope")],
            capture_output=True, text=True, encoding="utf-8",
        )
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_model_dir", payload["blockers"][0]["type"])

    def test_uncached_model_blocked_without_download(self):
        media = self.root / "clip.mp4"
        media.write_bytes(b"fixture")
        (code, result), _ = self.run_transcribe(media)
        self.assertEqual(2, code)
        self.assertEqual("blocked", result["status"])
        self.assertEqual("missing_cached_model", result["blockers"][0]["type"])

    def test_output_inside_material_pack_blocked(self):
        pack = self.root / "material-pack"
        (pack / "02_原始素材").mkdir(parents=True)
        media = pack / "02_原始素材" / "clip.mp4"
        media.write_bytes(b"fixture")
        args = [
            "--input", str(media),
            "--output", str(pack / "02_原始素材" / "transcript.json"),
            "--model-dir", str(self.model_dir),
            "--source-pack", str(pack),
        ]
        result = subprocess.run([str(PYTHON), str(TRANSCRIBE), *args], capture_output=True, text=True, encoding="utf-8")
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("output_inside_material_pack", payload["blockers"][0]["type"])


if __name__ == "__main__":
    unittest.main()
