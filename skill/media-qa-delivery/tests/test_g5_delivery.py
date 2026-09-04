import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "skill" / "media-qa-delivery" / "scripts" / "g5_build_delivery_manifest.py"
VALIDATE = ROOT / "skill" / "media-qa-delivery" / "scripts" / "g5_validate_delivery.py"
MIRROR = ROOT / "skill" / "media-qa-delivery" / "scripts" / "g5_mirror_audit_copy.py"


class G5DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name) / "bundle"; self.bundle.mkdir(); (self.bundle / "clips").mkdir(); (self.bundle / "failure-samples").mkdir()
        self.project = "fixture-g5"
        self.write("final-video.mp4", b"video"); self.write("cover.jpg", b"cover"); self.write("subtitles.srt", b"1\n00:00:00,000 --> 00:00:01,000\nHello\n")
        self.write("README.md", b"readme"); self.write("failure-samples/README.md", b"real failure\n")
        self.write("edit-timeline.md", b"| Segment | Output time | Source |\n| --- | --- | --- |\n")
        segments = []
        chapters = []
        for index in range(3):
            name = f"clips/chapter-{index + 1:02d}.mp4"; self.write(name, f"clip{index}".encode())
            segment = {"segmentId": f"s{index}", "assetId": "source-a", "sourceSha256": "A" * 64, "sourceStartMs": index * 1000, "sourceEndMs": (index + 1) * 1000}
            segments.append(segment); chapters.append({"chapterId": f"c{index}", "output": name, "segments": [segment["segmentId"]]})
        self.json("source-timecode-list.json", {"projectId": self.project, "chapters": chapters, "segments": segments})
        self.json("edit-plan.json", {"projectId": self.project, "editPlan": {"timeline": ["s0", "s1", "s2"]}, "humanReviewPoints": ["full_playback"], "evidenceRefs": ["G2-evidence.json"], "warnings": ["practice"]})
        artifacts = {"finalVideo": self.artifact("final-video.mp4"), "cover": self.artifact("cover.jpg"), "subtitles": self.artifact("subtitles.srt"), "chapterClips": [self.artifact(f"clips/chapter-{i + 1:02d}.mp4") for i in range(3)]}
        checks = {key: {"status": "pass"} for key in ("decode", "videoCodec", "dimensions", "fps", "audio", "duration", "blackFrames", "silence", "duplicateSegments", "cover")}
        self.json("metadata-validation-report.json", {"projectId": self.project, "status": "completed", "finishedAt": "2026-08-19", "checks": checks, "artifacts": artifacts})
        self.json("human-review-decision.json", {"projectId": self.project, "status": "approved", "decision": "accepted", "acceptedWarnings": []})
        self.json("export-config.json", {"projectId": self.project, "authorization": "fixture", "distribution": "not_for_distribution"})
        self.evidence = self.bundle.parent / "evidence.json"; self.evidence.write_text(json.dumps({"sourceEvidence": [{"assetId": "source-a", "sha256": "A" * 64, "sourceProbe": {"durationMs": 3000}}]}), encoding="utf-8")

    def write(self, name, content):
        path = self.bundle / name; path.write_bytes(content)

    def json(self, name, value):
        (self.bundle / name).write_text(json.dumps(value), encoding="utf-8")

    def artifact(self, name):
        data = (self.bundle / name).read_bytes(); return {"path": name, "sha256": hashlib.sha256(data).hexdigest().upper()}

    def run_cli(self, script, *args, code=0):
        result = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, code, result.stdout + result.stderr); return json.loads(result.stdout)

    def test_build_and_validate_bundle(self):
        self.run_cli(BUILD, "--bundle", self.bundle, "--evidence", self.evidence)
        result = self.run_cli(VALIDATE, "--bundle", self.bundle)
        self.assertEqual(result["status"], "valid")

    def test_rejects_hash_or_human_review_failure(self):
        self.run_cli(BUILD, "--bundle", self.bundle, "--evidence", self.evidence)
        self.write("cover.jpg", b"tampered")
        result = self.run_cli(VALIDATE, "--bundle", self.bundle, code=2)
        self.assertIn("sha256 mismatch: cover.jpg", result["errors"])

    def test_rejects_missing_human_approval(self):
        self.run_cli(BUILD, "--bundle", self.bundle, "--evidence", self.evidence)
        self.json("human-review-decision.json", {"projectId": self.project, "status": "pending", "decision": "pending"})
        result = self.run_cli(VALIDATE, "--bundle", self.bundle, code=2)
        self.assertIn("completed bundle lacks accepted human review", result["errors"])

    def test_rejects_invalid_chapter_count(self):
        self.run_cli(BUILD, "--bundle", self.bundle, "--evidence", self.evidence)
        trace = json.loads((self.bundle / "source-timecode-list.json").read_text(encoding="utf-8"))
        trace["chapters"] = trace["chapters"][:2]
        self.json("source-timecode-list.json", trace)
        result = self.run_cli(VALIDATE, "--bundle", self.bundle, code=2)
        self.assertIn("chapter clip count must be 3 to 5", result["errors"])

    def test_rejects_missing_required_edit_timeline(self):
        self.run_cli(BUILD, "--bundle", self.bundle, "--evidence", self.evidence)
        (self.bundle / "edit-timeline.md").unlink()
        result = self.run_cli(VALIDATE, "--bundle", self.bundle, code=2)
        self.assertIn("missing required file: edit-timeline.md", result["errors"])

    def test_mirror_replaces_stale_artifacts(self):
        self.run_cli(BUILD, "--bundle", self.bundle, "--evidence", self.evidence)
        audit = self.bundle.parent / "audit" / self.bundle.name; audit.mkdir(parents=True)
        (audit / "obsolete.txt").write_text("stale", encoding="utf-8")
        self.run_cli(MIRROR, "--source-bundle", self.bundle, "--audit-root", audit.parent)
        self.assertFalse((audit / "obsolete.txt").exists())


if __name__ == "__main__": unittest.main()
