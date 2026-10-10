import hashlib
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

    # ---- Issue ③ (zaku-003 库内批次全 0 分) ----
    # 库内导出/手动登记的候选没有 decodeProbe 字段。报告在场 = 分析器真解码成功的证据，
    # 但必须按 source.sha256 逐字对上候选身份才作数；显式 failed 的探针记录是机器失败
    # 事实，不被旧报告翻案。以下四例复用既有 run_recommend()，不新增任何子进程调用。

    def rewrite_pool(self, candidates):
        self.pool.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")

    def test_missing_probe_scores_via_matched_report(self):
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool[0].pop("decodeProbe")
        self.rewrite_pool(pool)
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        top = [item for item in payload["ranked"] if item["title"] == "good-track"][0]
        self.assertEqual(1.0, top["score"])
        self.assertIn("decode_via_analysis", top["notes"])

    def test_explicit_failed_probe_not_overridden_by_report(self):
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool[0]["decodeProbe"] = {"status": "failed", "error": "undecodable"}
        self.rewrite_pool(pool)
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        top = [item for item in payload["ranked"] if item["title"] == "good-track"][0]
        self.assertEqual(0.0, top["score"])
        self.assertIn("decode_probe_not_passed", top["notes"])
        self.assertNotIn("decode_via_analysis", top["notes"])

    def test_no_probe_and_no_report_still_unanalyzed(self):
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        item = candidate("C" * 64, "no-probe-no-report", "cc0")
        item.pop("decodeProbe")
        pool.append(item)
        self.rewrite_pool(pool)
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(["no-probe-no-report"], [x["title"] for x in payload["unanalyzed"]])
        self.assertEqual(2, len(payload["ranked"]))

    def test_byte_identity_scores_without_sha_field(self):
        # 候选只带 audioPath 文件、无 sha256 字段：按文件字节算身份 sha，报告同 sha 在场 → 作证成立
        audio = self.root / "track.mp3"
        audio.write_bytes(b"fake-audio-bytes-for-identity")
        sha = hashlib.sha256(audio.read_bytes()).hexdigest().upper()
        (self.reports / f"BGM-分析报告-{sha[:8]}.json").write_text(
            json.dumps(report(sha, 200000, 90, 4, -12)), encoding="utf-8")
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool.append({"title": "file-only-candidate", "licenseType": "cc0", "audioPath": str(audio)})
        self.rewrite_pool(pool)
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        top = [item for item in payload["ranked"] if item["title"] == "file-only-candidate"][0]
        self.assertEqual(1.0, top["score"])
        self.assertIn("decode_via_analysis", top["notes"])


    # ---- 台账②（banshee-001，甲案）：候选自带 reportPath 采信通道 ----

    def test_self_report_path_rescues_pool_when_dir_scan_misses(self):
        # banshee 实况：报告在别的节点目录、--reports-dir 扫不到；候选自带路径必须被读
        elsewhere = self.root / "G1-创作方向" / "analysis-C0C0C0C0"
        elsewhere.mkdir(parents=True)
        sha = "C" * 64
        (elsewhere / "BGM-分析报告-self.json").write_text(
            json.dumps(report(sha, 200000, 90, 4, -12)), encoding="utf-8")
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        item = {"sha256": sha, "title": "self-path-track", "licenseType": "cc0",
                "reportPath": str(elsewhere / "BGM-分析报告-self.json")}
        pool.append(item)
        self.rewrite_pool(pool)
        result = self.run_recommend()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual([], payload["unanalyzed"])
        top = [x for x in payload["ranked"] if x["title"] == "self-path-track"][0]
        self.assertEqual(1.0, top["score"])
        self.assertIn("decode_via_analysis", top["notes"])
        self.assertIn("decode_via_reportPath", top["notes"])

    def test_dir_scan_preferred_no_double_stamp(self):
        # 报告同时在扫描目录与 reportPath：走目录通道，不重复盖 reportPath 戳
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool[0].pop("decodeProbe")
        pool[0]["reportPath"] = str(self.reports / "BGM-分析报告-good.json")
        self.rewrite_pool(pool)
        result = self.run_recommend()
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        top = [x for x in payload["ranked"] if x["title"] == "good-track"][0]
        self.assertIn("decode_via_analysis", top["notes"])
        self.assertNotIn("decode_via_reportPath", top["notes"])

    def test_report_path_missing_file_named_not_silently_zeroed(self):
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool.append({"sha256": "D" * 64, "title": "ghost-report", "licenseType": "cc0",
                     "reportPath": str(self.root / "nowhere" / "BGM-分析报告-x.json")})
        self.rewrite_pool(pool)
        result = self.run_recommend()
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        entry = [x for x in payload["unanalyzed"] if x["title"] == "ghost-report"][0]
        self.assertEqual("missing", entry["reportPathStatus"])

    def test_report_path_sha_mismatch_named(self):
        stray = self.root / "stray-report.json"
        stray.write_text(json.dumps(report("E" * 64, 200000, 90, 4, -12)), encoding="utf-8")
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool.append({"sha256": "F" * 64, "title": "mismatched-report", "licenseType": "cc0",
                     "reportPath": str(stray)})
        self.rewrite_pool(pool)
        result = self.run_recommend()
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        entry = [x for x in payload["unanalyzed"] if x["title"] == "mismatched-report"][0]
        self.assertEqual("sha_mismatch", entry["reportPathStatus"])

    def test_report_path_failed_probe_red_line_still_holds(self):
        # ③ 保守红线不因新通道松动：显式 failed 探针不许被自带报告翻案
        elsewhere = self.root / "rescue"
        elsewhere.mkdir()
        sha = "9" * 64
        (elsewhere / "r.json").write_text(json.dumps(report(sha, 200000, 90, 4, -12)), encoding="utf-8")
        pool = json.loads(self.pool.read_text(encoding="utf-8"))["candidates"]
        pool.append({"sha256": sha, "title": "failed-probe", "licenseType": "cc0",
                     "decodeProbe": {"status": "failed", "error": "undecodable"},
                     "reportPath": str(elsewhere / "r.json")})
        self.rewrite_pool(pool)
        result = self.run_recommend()
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        item = [x for x in payload["ranked"] if x["title"] == "failed-probe"][0]
        self.assertEqual(0.0, item["score"])
        self.assertIn("decode_probe_not_passed", item["notes"])
        self.assertNotIn("decode_via_reportPath", item["notes"])


if __name__ == "__main__":
    unittest.main()
