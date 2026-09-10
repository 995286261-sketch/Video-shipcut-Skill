import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RENDER = ROOT / "skill" / "local-video-render" / "scripts" / "g4_render.py"


class G4RenderProfileTest(unittest.TestCase):
    def test_preserve_source_uses_vertical_canvas(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = root / "pack"
            raw = pack / "raw"
            raw.mkdir(parents=True)
            source = raw / "vertical.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=24", "-t", "1", "-c:v", "libx264", "-an", str(source)],
                check=True,
                capture_output=True,
            )
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "status": "prepared_for_render",
                "segments": [{
                    "segmentId": "vertical",
                    "source": {"relativePath": "raw/vertical.mp4", "startMs": 0, "endMs": 1000},
                    "timeline": {"startMs": 0, "endMs": 1000},
                    "output": {"filename": "seg-001.mp4"},
                }],
            }), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RENDER), "--manifest", str(manifest), "--source-pack", str(pack), "--output-dir", str(root / "out")],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual("preserve_source", payload["aspectRatioPolicy"])
            self.assertEqual({"width": 360, "height": 640}, payload["canvas"])
            # Issue 030: segments land in the contracted clean-segments/ subdirectory.
            self.assertEqual(str(root / "out" / "clean-segments"), payload["segmentsDir"])
            self.assertTrue((root / "out" / "clean-segments" / "seg-001.mp4").is_file())
            self.assertFalse((root / "out" / "seg-001.mp4").exists())

    def make_pack_and_manifest(self, root):
        raw = root / "pack" / "raw"
        raw.mkdir(parents=True)
        (raw / "a.mp4").write_bytes(b"not-a-real-video-but-dry-run-only")
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "status": "prepared_for_render", "projectId": "mask-test",
            "segments": [
                {"segmentId": "seg-011", "source": {"relativePath": "raw/a.mp4", "startMs": 0, "endMs": 1000},
                 "timeline": {"startMs": 0, "endMs": 1000}, "output": {"filename": "seg-011.mp4"}},
                {"segmentId": "seg-012", "source": {"relativePath": "raw/a.mp4", "startMs": 2000, "endMs": 12000},
                 "timeline": {"startMs": 1000, "endMs": 11000}, "output": {"filename": "seg-012.mp4"}},
            ],
        }), encoding="utf-8")
        return manifest

    def make_mask_doc(self, root, segment_id="seg-012", project_id="mask-test"):
        mask = root / "mask.json"
        mask.write_text(json.dumps({
            "schemaVersion": "0.1", "node": "G4", "projectId": project_id,
            "canvas": {"width": 1920, "height": 1080},
            "masks": [{"maskId": "src-cap-01", "segmentId": segment_id,
                       "outputFromMs": 2200, "outputToMs": 6200, "bandYpx": [950, 1080]}],
        }), encoding="utf-8")
        return mask

    def run_dry(self, root, manifest, mask):
        result = subprocess.run(
            [sys.executable, str(RENDER), "--manifest", str(manifest), "--source-pack", str(root / "pack"),
             "--output-dir", str(root / "out"), "--aspect-ratio-policy", "explicit", "--width", "1920", "--height", "1080",
             "--source-mask", str(mask), "--dry-run"],
            capture_output=True, text=True,
        )
        return result

    def test_source_mask_applies_windowed_ratio_drawbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.make_pack_and_manifest(root)
            result = self.run_dry(root, manifest, self.make_mask_doc(root))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            commands = json.loads(result.stdout)["commands"]
            graph = " ".join(commands[1])  # seg-012 command
            self.assertIn("drawbox", graph)
            # 950/1080 band as an ih ratio; window converted from output ms to slice-local seconds
            self.assertIn("y=trunc(ih*0.879630)", graph)
            self.assertIn("enable='between(t,1.200,5.200)'", graph)
            self.assertNotIn("drawbox", " ".join(commands[0]))  # seg-011 untouched

    def test_mask_targeting_unknown_segment_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.make_pack_and_manifest(root)
            result = self.run_dry(root, manifest, self.make_mask_doc(root, segment_id="seg-999"))
            self.assertEqual(2, result.returncode)
            self.assertIn("unknown segment", result.stdout)

    def test_mask_project_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.make_pack_and_manifest(root)
            result = self.run_dry(root, manifest, self.make_mask_doc(root, project_id="other-project"))
            self.assertEqual(2, result.returncode)
            self.assertIn("projectId does not match", result.stdout)

    def test_explicit_profile_requires_both_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"status": "prepared_for_render", "segments": []}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RENDER), "--manifest", str(manifest), "--source-pack", str(root), "--output-dir", str(root / "out"), "--aspect-ratio-policy", "explicit", "--width", "1080"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("requires --width and --height", result.stdout)


if __name__ == "__main__":
    unittest.main()
