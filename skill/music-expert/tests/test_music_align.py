import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/music-expert/scripts/music_align.py"
PYTHON = sys.executable


def report_json(top_segment=(120000, 160000), track_ms=200000):
    return {
        "schemaVersion": "0.1",
        "cacheKey": "R" * 64,
        "source": {"sha256": "R" * 64, "path": "/somewhere/track.mp3", "decodedDurationMs": track_ms},
        "tempoBpm": 90.0,
        "energySegments": [
            {"startMs": 0, "endMs": 60000, "energyMean": 0.1},
            {"startMs": top_segment[0], "endMs": top_segment[1], "energyMean": 0.5},
        ],
        "hitPoints": [{"tMs": t, "kind": "beat"} for t in range(1000, track_ms, 2000)],
    }


def brief_json():
    return {
        "projectId": "align-test",
        "measuredTotalDurationMs": 100000,
        "sentences": [
            {"sentenceId": "S01", "startMs": 0, "durationMs": 30000},
            {"sentenceId": "S02", "startMs": 30000, "durationMs": 30000},
            {"sentenceId": "S03", "startMs": 60000, "durationMs": 40000},
        ],
    }


class MusicAlignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.write_inputs()

    def tearDown(self):
        self.temp.cleanup()

    def write_inputs(self, report=None, brief=None):
        self.report = self.root / "report.json"
        self.brief = self.root / "brief.json"
        self.report.write_text(json.dumps(report or report_json()), encoding="utf-8")
        self.brief.write_text(json.dumps(brief or brief_json()), encoding="utf-8")

    def run_align(self, extra=(), timeline=100000):
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--report", str(self.report), "--voice-brief", str(self.brief),
             "--timeline-ms", str(timeline), "--output-dir", str(self.out), *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def load_result(self):
        return json.loads((self.out / "BGM-对齐建议-v0.2.json").read_text(encoding="utf-8"))

    def test_climax_sentence_places_top_energy_segment(self):
        # top segment center 140000, S03 center 80000 -> offset 60000, window [60000,100000]
        result = self.run_align(("--climax-sentence", "S03",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("completed", payload["status"])
        alignment = self.load_result()["alignment"]
        self.assertEqual(60000, alignment["offsetMs"])
        self.assertEqual(0, alignment["clampedDeviationMs"])
        self.assertEqual([60000, 100000], alignment["topSegmentOnTimeline"])
        self.assertEqual("S03", alignment["climaxAnchorSentence"])

    def test_negative_raw_offset_clamps_to_zero_with_deviation(self):
        # top center 30000, S03 center 80000 -> raw -50000 -> offset 0, deviation +50000
        self.write_inputs(report=report_json(top_segment=(10000, 50000)))
        result = self.run_align(("--climax-sentence", "S03",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        alignment = self.load_result()["alignment"]
        self.assertEqual(-50000, alignment["rawOffsetMs"])
        self.assertEqual(0, alignment["offsetMs"])
        self.assertEqual(50000, alignment["clampedDeviationMs"])

    def test_default_offset_without_climax_and_short_track_blocked(self):
        result = self.run_align()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(0, self.load_result()["alignment"]["offsetMs"])
        short = self.run_align(timeline=300000)  # track 200000ms < timeline
        self.assertEqual(2, short.returncode)
        payload = json.loads(short.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("track_cannot_cover_timeline", payload["blockers"][0]["type"])

    def test_snap_hits_and_misses_reported_honestly(self):
        # boundaries at 0/30000/60000 (last end skipped); hitPoints at odd 1000s,
        # with offset 0 every nearest hit is 1000ms away
        miss = self.run_align(("--snap-tolerance-ms", "500",))
        self.assertEqual(0, miss.returncode, miss.stdout + miss.stderr)
        result = self.load_result()
        self.assertEqual(0, len(result["snapped"]))
        self.assertTrue(all(item["nearestDistanceMs"] > 500 for item in result["missed"]))
        # same grid but tolerance 1500 -> every boundary snaps within a beat
        hit = self.run_align(("--snap-tolerance-ms", "1500",))
        self.assertEqual(0, hit.returncode, hit.stdout + hit.stderr)
        result = self.load_result()
        self.assertEqual(5, len(result["snapped"]))
        self.assertEqual(0, len(result["missed"]))
        for item in result["snapped"]:
            self.assertEqual(0, item["hitPointTimelineMs"] % 1000)

    def test_echo_card_written_with_timecodes(self):
        result = self.run_align(("--climax-sentence", "S03",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        echo = Path(json.loads(result.stdout)["echo"])
        text = echo.read_text(encoding="utf-8")
        self.assertIn("# BGM 对齐回显 — track.mp3", text)
        self.assertIn("从音轨 1:00.000 起铺", text)
        self.assertIn("S03", text)
        self.assertIn("BGM-对齐建议-v0.2.json", text)
        self.assertIn("## 乐句表（机器版", text)
        self.assertIn("## 逐句排版档位（机械草稿", text)

    def test_sentence_overrunning_timeline_is_invalid(self):
        brief = brief_json()
        brief["sentences"][-1]["durationMs"] = 50000  # ends at 110000 > timeline
        self.write_inputs(brief=brief)
        result = self.run_align()
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", json.loads(result.stdout)["status"])

    def test_unknown_climax_sentence_is_invalid(self):
        result = self.run_align(("--climax-sentence", "S99",))
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("climaxSentence", payload["errors"][0]["field"])


def staircase_report():
    return {
        "schemaVersion": "0.1",
        "cacheKey": "R" * 64,
        "source": {"sha256": "R" * 64, "path": "/somewhere/track.mp3", "decodedDurationMs": 200000},
        "tempoBpm": 90.0,
        "energySegments": [
            {"startMs": 0, "endMs": 50000, "energyMean": 0.1},
            {"startMs": 50000, "endMs": 100000, "energyMean": 0.3},
            {"startMs": 100000, "endMs": 150000, "energyMean": 0.5},
            {"startMs": 150000, "endMs": 200000, "energyMean": 0.9},
        ],
        "hitPoints": [{"tMs": t, "kind": "beat"} for t in range(1000, 200000, 2000)],
    }


def staircase_brief():
    return {
        "projectId": "tier-test",
        "measuredTotalDurationMs": 200000,
        "sentences": [
            {"sentenceId": f"S0{i}", "startMs": (i - 1) * 50000, "durationMs": 50000} for i in range(1, 5)
        ],
    }


class LayoutTierTests(unittest.TestCase):
    """v0.2: per-sentence layoutTier drafts + machine phrase table on the timeline."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.write_inputs(report=staircase_report(), brief=staircase_brief())

    def tearDown(self):
        self.temp.cleanup()

    def write_inputs(self, report, brief):
        self.report = self.root / "report.json"
        self.brief = self.root / "brief.json"
        self.report.write_text(json.dumps(report), encoding="utf-8")
        self.brief.write_text(json.dumps(brief), encoding="utf-8")

    def run_align(self, extra=(), timeline=200000):
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--report", str(self.report), "--voice-brief", str(self.brief),
             "--timeline-ms", str(timeline), "--output-dir", str(self.out), *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def load_result(self):
        return json.loads((self.out / "BGM-对齐建议-v0.2.json").read_text(encoding="utf-8"))

    def test_segment_quantile_rule_drafts_all_four_tiers(self):
        # used energies [0.1,0.3,0.5,0.9]: q75=0.6 q50=0.4 q25=0.25
        result = self.run_align()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        layout = self.load_result()["layout"]
        self.assertEqual(["快切", "推进", "常规", "留白"], layout["tierVocabulary"])
        self.assertEqual([0.6, 0.4, 0.25], layout["rule"]["cutoffs"])
        drafts = {item["sentenceId"]: item["layoutTierDraft"] for item in layout["perSentence"]}
        self.assertEqual({"S01": "留白", "S02": "常规", "S03": "推进", "S04": "快切"}, drafts)

    def test_tier_quantiles_are_adjustable(self):
        result = self.run_align(("--tier-quantiles", "0.9,0.6,0.3",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        layout = self.load_result()["layout"]
        # sorted [0.1,0.3,0.5,0.9]: q90=0.78 q60=0.46 q30=0.28 -> 0.9快切 0.5推进 0.3常规 0.1留白
        drafts = {item["sentenceId"]: item["layoutTierDraft"] for item in layout["perSentence"]}
        self.assertEqual({"S01": "留白", "S02": "常规", "S03": "推进", "S04": "快切"}, drafts)
        self.assertEqual([0.78, 0.46, 0.28], layout["rule"]["cutoffs"])

    def test_invalid_tier_quantiles_rejected(self):
        result = self.run_align(("--tier-quantiles", "0.5,0.6,0.1",))
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("tierQuantiles", payload["errors"][0]["field"])

    def test_flat_energy_falls_back_to_regular(self):
        report = staircase_report()
        for seg in report["energySegments"]:
            seg["energyMean"] = 0.4
        self.write_inputs(report, staircase_brief())
        self.run_align()
        layout = self.load_result()["layout"]
        self.assertIsNone(layout["rule"]["cutoffs"])
        self.assertEqual("常规", layout["rule"]["flatFallback"])
        self.assertTrue(all(item["layoutTierDraft"] == "常规" for item in layout["perSentence"]))

    def test_machine_phrase_table_maps_track_to_timeline(self):
        # brief fits 140000ms; climax T02 center 105000 vs top segment center 175000 -> raw 70000
        # clamps to max_offset 60000, so the track's first 60s never appear on the timeline
        brief = {"projectId": "phrase-test", "sentences": [
            {"sentenceId": "T01", "startMs": 0, "durationMs": 70000},
            {"sentenceId": "T02", "startMs": 70000, "durationMs": 70000},
        ]}
        self.write_inputs(staircase_report(), brief)
        result = self.run_align(("--climax-sentence", "T02", "--timeline-ms", "140000"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        layout = self.load_result()["layout"]
        self.assertEqual(60000, self.load_result()["alignment"]["offsetMs"])
        phrases = layout["phrasesOnTimeline"]
        self.assertEqual(3, len(phrases))  # track segments 2..4 survive the 60s skip
        self.assertEqual("P1", phrases[0]["phraseId"])
        self.assertEqual(50000, phrases[0]["trackStartMs"])
        self.assertEqual(0, phrases[0]["timelineStartMs"])
        self.assertEqual(40000, phrases[0]["timelineEndMs"])
        self.assertEqual(["T01"], phrases[0]["coversSentences"])
        self.assertEqual(["T01", "T02"], phrases[1]["coversSentences"])
        self.assertEqual(["T02"], phrases[2]["coversSentences"])
        self.assertTrue(all(p["timelineEndMs"] <= 140000 for p in phrases))


class BlueprintTests(unittest.TestCase):
    """N9 blueprint mode: no script yet — beat grid, phrase windows, sentence budgets."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.report = self.root / "report.json"
        self.report.write_text(json.dumps(staircase_report()), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_blueprint(self, extra=(), timeline=100000, brief=None):
        cmd = [PYTHON, str(SCRIPT), "--report", str(self.report), "--blueprint",
               "--timeline-ms", str(timeline), "--output-dir", str(self.out)]
        if brief is not None:
            cmd += ["--voice-brief", str(brief)]
        return subprocess.run(cmd + list(extra), capture_output=True, text=True, encoding="utf-8")

    def load_result(self):
        return json.loads((self.out / "BGM-节拍蓝图-v0.1.json").read_text(encoding="utf-8"))

    def test_mode_exclusivity_enforced(self):
        neither = subprocess.run(
            [PYTHON, str(SCRIPT), "--report", str(self.report), "--timeline-ms", "100000",
             "--output-dir", str(self.out)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(2, neither.returncode)
        self.assertEqual("mode", json.loads(neither.stdout)["errors"][0]["field"])
        brief = self.root / "brief.json"
        brief.write_text(json.dumps(staircase_brief()), encoding="utf-8")
        both = self.run_blueprint(brief=brief)
        self.assertEqual(2, both.returncode)
        self.assertEqual("mode", json.loads(both.stdout)["errors"][0]["field"])

    def test_climax_sentence_rejected_in_blueprint_mode(self):
        result = self.run_blueprint(("--climax-sentence", "S01",))
        self.assertEqual(2, result.returncode)
        self.assertEqual("climaxSentence", json.loads(result.stdout)["errors"][0]["field"])

    def test_phrases_carry_budget_hints_and_counts(self):
        # offset 0: used segments [0-50k]=0.1, [50-100k]=0.3; cutoffs q75=.25 q50=.2 q25=.15
        # -> 0.3 >= .25 快切 (budget 4-6, mid 5 -> 10 sentences); 0.1 < .15 留白 (8-12, mid 10 -> 5)
        result = self.run_blueprint()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("blueprint", payload["mode"])
        phrases = self.load_result()["phrases"]
        self.assertEqual(2, len(phrases))
        self.assertEqual(["留白", [8, 12], 5], [phrases[0]["layoutTierDraft"], phrases[0]["sentenceBudgetHintSec"], phrases[0]["suggestedSentenceCount"]])
        self.assertEqual(["快切", [4, 6], 10], [phrases[1]["layoutTierDraft"], phrases[1]["sentenceBudgetHintSec"], phrases[1]["suggestedSentenceCount"]])

    def test_climax_position_slides_track_and_grid_is_clipped(self):
        # top center 175000, position 25000 -> raw 150000, max offset 100000 -> clamped, deviation -50000
        result = self.run_blueprint(("--climax-position-ms", "25000",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = self.load_result()
        self.assertEqual(100000, payload["alignment"]["offsetMs"])
        self.assertEqual(-50000, payload["alignment"]["clampedDeviationMs"])
        grid = payload["beatGridMs"]
        self.assertEqual(50, len(grid))  # t-100000 in [0,100000]: 101000..199000 step 2000
        self.assertEqual(1000, grid[0])
        self.assertEqual(99000, grid[-1])
        # suggested boundary at phrase switch 50000: nearest grid beats 49000/51000 tie -> first
        boundary = payload["suggestedBoundaries"][0]
        self.assertEqual(50000, boundary["atMs"])
        self.assertEqual(49000, boundary["nearestBeatMs"])
        self.assertEqual(-1000, boundary["deltaMs"])

    def test_budget_map_is_adjustable_and_validated(self):
        result = self.run_blueprint(("--budget-map", "3-4,4-5,5-6,6-7",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"快切": [3, 4], "推进": [4, 5], "常规": [5, 6], "留白": [6, 7]},
                         self.load_result()["budgetMap"])
        bad = self.run_blueprint(("--budget-map", "6-4,4-5,5-6,6-7",))
        self.assertEqual(2, bad.returncode)
        self.assertEqual("budgetMap", json.loads(bad.stdout)["errors"][0]["field"])

    def test_blueprint_echo_card_sections(self):
        result = self.run_blueprint(("--climax-position-ms", "25000",))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = Path(json.loads(result.stdout)["echo"]).read_text(encoding="utf-8")
        self.assertIn("# BGM 节拍蓝图 — track.mp3", text)
        self.assertIn("每句预算", text)
        self.assertIn("建议句边界", text)
        self.assertIn("禁止拉伸音频踩点", text)


if __name__ == "__main__":
    unittest.main()
