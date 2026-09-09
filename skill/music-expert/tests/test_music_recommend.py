import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/music-expert/scripts/music_recommend.py"
PYTHON = sys.executable

GOOD_SHA = "A" * 64
WEAK_SHA = "B" * 64


def report(sha, duration_ms, bpm, segments, lufs):
    return {
        "schemaVersion": "0.1",
        "source": {"sha256": sha, "decodedDurationMs": duration_ms},
        "tempoBpm": bpm,
        "energySegments": [{"startMs": i * 10000, "endMs": (i + 1) * 10000} for i in range(segments)],
        "loudness": {"integratedLufs": lufs},
        "hitPoints": [{"tMs": 500, "kind": "beat"}],
    }


def candidate(sha, title, license_type):
    return {
        "sha256": sha, "title": title, "licenseType": license_type,
        "decodeProbe": {"status": "passed"}, "sourceUrl": f"https://example.invalid/{sha[:8]}",
        "attributionRequired": license_type == "cc-by",
    }


class MusicRecommendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.reports = self.root / "reports"
        self.reports.mkdir()
        (self.reports / f"BGM-分析报告-good.json").write_text(
            json.dumps(report(GOOD_SHA, 200000, 90, 4, -12)), encoding="utf-8")
        (self.reports / f"BGM-分析报告-weak.json").write_text(
            json.dumps(report(WEAK_SHA, 50000, 140, 2, -8)), encoding="utf-8")
        self.pool = self.root / "pool.json"
        self.pool.write_text(json.dumps({"candidates": [
            candidate(GOOD_SHA, "good-track", "cc0"),
            candidate(WEAK_SHA, "weak-track", "cc-by"),
        ]}), encoding="utf-8")
        self.profile = self.root / "profile.json"
        self.profile.write_text(json.dumps({
            "targetDurationSec": 100, "bpmRange": [80, 100], "minSegments": 3, "maxIntegratedLufs": -10,
        }), encoding="utf-8")
        self.output = self.root / "out" / "BGM-推荐-v0.1.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_recommend(self, extra=()):
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--profile", str(self.profile), "--candidates", str(self.pool),
             "--reports-dir", str(self.reports), "--output", str(self.output), *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_scores_and_ranks_deterministically(self):
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        ranked = payload["ranked"]
        self.assertEqual(["good-track", "weak-track"], [item["title"] for item in ranked])
        self.assertEqual(1.0, ranked[0]["score"])
        self.assertAlmostEqual(0.18, ranked[1]["score"])
        self.assertEqual(["good-track"], [item["title"] for item in payload["passing"]])
        self.assertEqual("3:20.000", ranked[0]["durationDisplay"])
        self.assertIn("bpm_out_of_range", ranked[1]["notes"])

    def test_insufficient_candidates_reports_gap_without_fabricating(self):
        result = self.run_recommend(("--min-pass", "3",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertFalse(payload["sufficiency"]["enough"])
        self.assertEqual(3, payload["sufficiency"]["minExpected"])
        self.assertIn("补检索", payload["sufficiency"]["gapAction"])

    def test_unanalyzed_candidate_is_flagged_not_scored(self):
        pool = json.loads(self.pool.read_text(encoding="utf-8"))
        pool["candidates"].append(candidate("C" * 64, "never-analyzed", "cc0"))
        self.pool.write_text(json.dumps(pool), encoding="utf-8")
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(["never-analyzed"], [item["title"] for item in payload["unanalyzed"]])
        self.assertIn("music_analyze.py", payload["unanalyzed"][0]["hint"])
        self.assertEqual(2, len(payload["ranked"]))

    def test_empty_pool_is_blocked(self):
        result = subprocess.run(
            [PYTHON, str(SCRIPT), "--profile", str(self.profile), "--output", str(self.output)],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", json.loads(result.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
