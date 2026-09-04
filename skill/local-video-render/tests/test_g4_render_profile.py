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
