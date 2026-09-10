import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/music-expert/scripts/music_mix_plan.py"
PYTHON = sys.executable


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class MusicMixPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bgm = self.root / "track.mp3"
        self.bgm.write_bytes(b"LOW-PHONK-fixture" * 100)
        self.report = self.root / "BGM-分析报告.json"
        self.report.write_text(json.dumps({"loudness": {"integratedLufs": -10.2}}), encoding="utf-8")
        self.alignment = self.root / "BGM-对齐建议-v0.2.json"
        self._write_alignment([
            {"sentenceId": "N01", "fromMs": 0, "toMs": 5000},
            {"sentenceId": "N02", "fromMs": 5000, "toMs": 12000},
        ])
        self.plan = self.root / "G3-剪辑计划-v0.1.json"
        self._write_plan()
        self.out = self.root / "G4-混音"

    def tearDown(self):
        self.temp.cleanup()

    def _write_alignment(self, ducking):
        self.alignment.write_text(json.dumps({
            "schemaVersion": "0.2", "purpose": "bgm_alignment",
            "inputs": {"reportCacheKey": {"sha256": sha256(self.bgm)}, "report": str(self.report)},
            "alignment": {"offsetMs": 0, "timelineMs": 12000},
            "fades": {"fadeInMs": 1000, "fadeOutStartMs": 11000, "fadeOutMs": 1000},
            "ducking": ducking,
        }, ensure_ascii=False), encoding="utf-8")

    def _write_plan(self, status="approved_for_g4"):
        self.plan.write_text(json.dumps({
            "node": "G3", "status": status, "projectId": "mix-test", "timelineDurationMs": 12000,
            "bgmPlan": {
                "audioSha256": sha256(self.bgm),
                "alignmentRef": str(self.alignment),
                "alignmentSha256": sha256(self.alignment),
                "trackOffsetMs": 0,
                "fades": {"fadeInMs": 1000, "fadeOutStartMs": 11000, "fadeOutMs": 1000},
            },
        }, ensure_ascii=False), encoding="utf-8")

    def run_plan(self, extra=()):
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--plan", str(self.plan), "--alignment", str(self.alignment),
             "--bgm-audio", str(self.bgm), "--output-dir", str(self.out), *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def contract(self):
        return json.loads((self.out / "BGM-混音合同-v0.1.json").read_text(encoding="utf-8"))

    def test_happy_path_merges_contiguous_ducking(self):
        result = self.run_plan()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("completed", payload["status"])
        self.assertEqual(1, payload["duckSegments"])  # 0-5000 + 5000-12000 merge
        contract = self.contract()
        self.assertEqual({"fromMs": 0, "toMs": 12000, "sentenceIds": ["N01", "N02"]}, contract["duckSegments"][0])
        self.assertEqual(-12.0, contract["bedGainDb"])
        self.assertEqual(6.0, contract["duckReductionDb"])
        # -10.2 -12 -6 = -28.2 LUFS: inside the audible window, recorded for G4 to verify
        self.assertEqual(-28.2, contract["predictedLufs"]["bedDuckedLufs"])
        self.assertEqual(sha256(self.bgm), contract["bgmAudio"]["sha256"])
        self.assertTrue((self.out / "BGM-混音合同回显-v0.1.md").is_file())

    def test_non_contiguous_ducking_stays_split(self):
        self._write_alignment([
            {"sentenceId": "N01", "fromMs": 0, "toMs": 5000},
            {"sentenceId": "N02", "fromMs": 6000, "toMs": 12000},
        ])
        self._write_plan()
        result = self.run_plan()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(2, self.contract()["duckSegments"] and len(self.contract()["duckSegments"]))

    def test_custom_duck_depth_is_parametric(self):
        result = self.run_plan(("--duck-reduction-db", "5", "--bed-gain-db", "-10"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(5.0, self.contract()["duckReductionDb"])
        self.assertEqual(-10.0, self.contract()["bedGainDb"])

    def test_inaudible_bed_is_refused_by_the_guard(self):
        # the exact zaku failure: -18 bed + 12 duck on a -10.2 LUFS track = -40.2,
        # "mixed in" but inaudible — the contract must refuse to exist
        result = self.run_plan(("--bed-gain-db", "-18", "--duck-reduction-db", "12"))
        self.assertEqual(2, result.returncode)
        fields = [error["field"] for error in json.loads(result.stdout)["errors"]]
        self.assertIn("mixAudibility", fields)

    def test_unmeasured_track_is_refused_by_the_guard(self):
        self.report.write_text(json.dumps({}), encoding="utf-8")
        result = self.run_plan()
        self.assertEqual(2, result.returncode)
        fields = [error["field"] for error in json.loads(result.stdout)["errors"]]
        self.assertIn("mixAudibility", fields)

    def test_unapproved_plan_is_rejected(self):
        self._write_plan(status="review_required")
        result = self.run_plan()
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertIn("approved_for_g4", payload["errors"][0]["error"])

    def test_wrong_bgm_take_is_rejected(self):
        other = self.root / "other.mp3"
        other.write_bytes(b"different-take" * 50)
        result = subprocess.run(
            [PYTHON, str(SCRIPT), "--plan", str(self.plan), "--alignment", str(self.alignment),
             "--bgm-audio", str(other), "--output-dir", str(self.out)],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(2, result.returncode)
        fields = [error["field"] for error in json.loads(result.stdout)["errors"]]
        self.assertIn("audioSha256", fields)

    def test_tampered_alignment_artifact_is_rejected(self):
        data = json.loads(self.alignment.read_text(encoding="utf-8"))
        data["alignment"]["offsetMs"] = 4100  # hand-edit after the plan was approved
        self.alignment.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = self.run_plan()
        self.assertEqual(2, result.returncode)
        fields = [error["field"] for error in json.loads(result.stdout)["errors"]]
        self.assertIn("alignmentSha256", fields)

    def test_fade_beyond_timeline_is_rejected(self):
        data = json.loads(self.alignment.read_text(encoding="utf-8"))
        data["fades"]["fadeOutStartMs"] = 12000
        self.alignment.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.plan.write_text(json.dumps({
            "node": "G3", "status": "approved_for_g4", "projectId": "mix-test", "timelineDurationMs": 12000,
            "bgmPlan": {
                "audioSha256": sha256(self.bgm),
                "alignmentRef": str(self.alignment),
                "alignmentSha256": sha256(self.alignment),
                "trackOffsetMs": 0,
                "fades": {"fadeInMs": 1000, "fadeOutStartMs": 12000, "fadeOutMs": 1000},
            },
        }, ensure_ascii=False), encoding="utf-8")
        result = self.run_plan()
        self.assertEqual(2, result.returncode)
        fields = [error["field"] for error in json.loads(result.stdout)["errors"]]
        self.assertIn("fades", fields)

    def test_out_of_range_gains_are_rejected(self):
        result = self.run_plan(("--bed-gain-db", "-1"))
        self.assertEqual(2, result.returncode)
        fields = [error["field"] for error in json.loads(result.stdout)["errors"]]
        self.assertIn("bedGainDb", fields)


if __name__ == "__main__":
    unittest.main()
