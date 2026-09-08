import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFY_SCRIPT = ROOT / "skill/video-edit-plan/scripts/g3_extract_verification_frames.py"
KEYFRAME_SCRIPT = ROOT / "skill/video-edit-plan/scripts/g3_extract_visual_analysis_keyframes.py"
PYTHON = sys.executable


class FrameExtractionTests(unittest.TestCase):
    """Issue 022: ffmpeg may exit 0 without writing a frame; extractors must check the file."""

    def setUp(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg is required")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        (self.pack / "raw").mkdir(parents=True)
        self.source = self.pack / "raw/clip.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:r=10", "-t", "2", "-c:v", "libx264", "-an", str(self.source)],
            check=True, capture_output=True,
        )
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest().upper()
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text(json.dumps({
            "schemaVersion": "0.1", "node": "G2", "projectId": "demo-001",
            "sourceEvidence": [{"assetId": "clip-1", "relativePath": "raw/clip.mp4", "sha256": digest, "sourceProbe": {"durationMs": 2000}}],
        }), encoding="utf-8")
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({
            "schemaVersion": "0.1", "node": "G3", "projectId": "demo-001", "status": "review_required",
            "segments": [{"segmentId": "seg-001", "assetId": "clip-1", "startMs": 0, "endMs": 1000, "reason": "r", "evidenceRefs": ["e"]}],
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def silent_ffmpeg_env(self):
        """A PATH shim where ffmpeg always exits 0 without producing any file."""
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        shim = bin_dir / "ffmpeg"
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        shim.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        return env

    def run_args(self, args, env=None):
        return subprocess.run([PYTHON, *[str(a) for a in args]], capture_output=True, text=True, encoding="utf-8", env=env)

    def verify_args(self, output_dir):
        return [str(VERIFY_SCRIPT), "--plan", str(self.plan), "--evidence", str(self.evidence), "--source-pack", str(self.pack), "--output-dir", str(output_dir)]

    def keyframe_args(self, output_dir):
        return [str(KEYFRAME_SCRIPT), "--evidence", str(self.evidence), "--asset-id", "clip-1", "--source-pack", str(self.pack), "--output-dir", str(output_dir), "--interval-ms", "1000"]

    def test_verification_frames_exist_on_disk(self):
        out = self.root / "verify-frames"
        result = self.run_args(self.verify_args(out))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        manifest = json.loads((out / "G3-visual-verification-frames.json").read_text(encoding="utf-8"))
        frames = manifest["segments"][0]["frames"]
        self.assertEqual(3, len(frames))
        for frame in frames:
            path = Path(frame["path"])
            self.assertTrue(path.is_file() and path.stat().st_size > 0, frame["path"])

    def test_keyframes_exist_on_disk(self):
        out = self.root / "keyframes"
        result = self.run_args(self.keyframe_args(out))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        manifest = json.loads((out / "G3-目标素材视觉分析-v0.1.json").read_text(encoding="utf-8"))
        frames = manifest["targetAssets"][0]["keyframes"]
        self.assertTrue(frames)
        for frame in frames:
            path = Path(frame["path"])
            self.assertTrue(path.is_file() and path.stat().st_size > 0, frame["path"])

    def keyframe_summary(self, result):
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_keyframe_cache_hit_skips_reextraction(self):
        out = self.root / "keyframes-cache"
        first = self.keyframe_summary(self.run_args(self.keyframe_args(out)))
        second = self.keyframe_summary(self.run_args(self.keyframe_args(out)))
        self.assertEqual("keyframes_ready", first["status"])
        self.assertEqual("cache_hit", second["status"])
        self.assertEqual(first["manifest"], second["manifest"])
        self.assertEqual(first["frames"], second["frames"])

    def test_interval_change_is_a_cache_miss_and_keeps_old_manifest(self):
        out = self.root / "keyframes-interval"
        self.keyframe_summary(self.run_args(self.keyframe_args(out)))
        changed = self.keyframe_args(out)
        changed[changed.index("--interval-ms") + 1] = "2000"
        second = self.keyframe_summary(self.run_args(changed))
        self.assertEqual("keyframes_ready", second["status"])
        self.assertTrue((out / "G3-目标素材视觉分析-v0.1.json").is_file())
        self.assertTrue((out / "G3-目标素材视觉分析-v0.2.json").is_file())
        self.assertNotIn("v0.1", second["manifest"])
        # The original interval still hits its own cached manifest afterwards.
        third = self.keyframe_summary(self.run_args(self.keyframe_args(out)))
        self.assertEqual("cache_hit", third["status"])

    def test_incomplete_frame_cache_is_regenerated_in_place(self):
        out = self.root / "keyframes-broken-cache"
        first = self.keyframe_summary(self.run_args(self.keyframe_args(out)))
        manifest = json.loads(Path(first["manifest"]).read_text(encoding="utf-8"))
        Path(manifest["targetAssets"][0]["keyframes"][0]["path"]).unlink()
        second = self.keyframe_summary(self.run_args(self.keyframe_args(out)))
        self.assertEqual("keyframes_ready", second["status"])
        self.assertEqual(first["manifest"], second["manifest"])
        self.assertEqual(1, len(list(out.glob("G3-目标素材视觉分析-v*.json"))))
        regenerated = json.loads(Path(second["manifest"]).read_text(encoding="utf-8"))
        for frame in regenerated["targetAssets"][0]["keyframes"]:
            self.assertTrue(Path(frame["path"]).is_file(), frame["path"])

    def test_verification_silent_ffmpeg_is_rejected(self):
        out = self.root / "verify-silent"
        result = self.run_args(self.verify_args(out), env=self.silent_ffmpeg_env())
        self.assertNotEqual(0, result.returncode)
        self.assertIn("without producing frame file", result.stdout)

    def test_keyframes_silent_ffmpeg_is_rejected(self):
        out = self.root / "keyframes-silent"
        result = self.run_args(self.keyframe_args(out), env=self.silent_ffmpeg_env())
        self.assertNotEqual(0, result.returncode)
        self.assertIn("without producing keyframe file", result.stdout)

    def test_boundary_end_frame_steps_back_and_is_recorded(self):
        """Issue 022 fallback: ffmpeg exits 0 without writing near the source end."""
        real = shutil.which("ffmpeg")
        bin_dir = self.root / "shim2"
        bin_dir.mkdir(exist_ok=True)
        shim = bin_dir / "ffmpeg"
        shim.write_text(
            "#!/bin/sh\n"
            'ss=""\nprev=""\nfor a in "$@"; do [ "$prev" = "-ss" ] && ss="$a"; prev="$a"; done\n'
            'if [ -n "$ss" ] && awk -v s="$ss" -v c="$SILENT_ABOVE" "BEGIN{exit !(s+0>=c+0)}"; then exit 0; fi\n'
            f'exec "{real}" "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        env["SILENT_ABOVE"] = "1.5"
        plan = self.root / "boundary-plan.json"
        plan.write_text(json.dumps({
            "schemaVersion": "0.1", "node": "G3", "projectId": "demo-001", "status": "review_required",
            "segments": [{"segmentId": "seg-001", "assetId": "clip-1", "startMs": 0, "endMs": 2000, "reason": "r", "evidenceRefs": ["e"]}],
        }), encoding="utf-8")
        out = self.root / "boundary-frames"
        result = self.run_args([str(VERIFY_SCRIPT), "--plan", str(plan), "--evidence", str(self.evidence), "--source-pack", str(self.pack), "--output-dir", str(out)], env=env)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        manifest = json.loads((out / "G3-visual-verification-frames.json").read_text(encoding="utf-8"))
        end_frame = next(frame for frame in manifest["segments"][0]["frames"] if frame["label"] == "end")
        self.assertEqual(1999, end_frame["requestedSourceMs"])
        self.assertEqual(1499, end_frame["sourceMs"])
        self.assertTrue(Path(end_frame["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
