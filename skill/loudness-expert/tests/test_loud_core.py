"""loud_core 纯函数回归（无 ffmpeg 依赖层）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import loud_core  # noqa: E402

SUMMARY_FIXTURE = """
[Parsed_ebur128 @ 0x60000] Summary:
  Integrated loudness:
    I:         -16.1 LUFS
    Threshold: -26.4 LUFS
  Loudness range:
    LRA:         8.4 LU
    Threshold: -36.5 LUFS
  True peak:
    Peak:      -2.3 dBFS
"""

SENTINEL_FIXTURE = """
    I:         -70.0 LUFS
    Peak:      -100.0 dBFS
"""


class ParseTests(unittest.TestCase):
    def test_reads_last_summary_block(self):
        parsed = loud_core.parse_ebur128_text("旧块 I: -3.0 LUFS\n" + SUMMARY_FIXTURE)
        self.assertEqual(parsed["integratedLufs"], -16.1)
        self.assertEqual(parsed["truePeakDbtp"], -2.3)
        self.assertEqual(parsed["loudnessRangeLu"], 8.4)

    def test_rejects_silence_sentinels(self):
        parsed = loud_core.parse_ebur128_text(SENTINEL_FIXTURE)
        self.assertIsNone(parsed["integratedLufs"])
        self.assertIsNone(parsed["truePeakDbtp"])

    def test_missing_fields_are_none_not_zero(self):
        parsed = loud_core.parse_ebur128_text("无汇总")
        self.assertEqual(parsed, {"integratedLufs": None, "truePeakDbtp": None,
                                  "loudnessRangeLu": None})


class FeasibilityTests(unittest.TestCase):
    PROFILE = dict(loud_core.PROFILES["video"])

    def test_feasible_raise_with_headroom(self):
        verdict = loud_core.linear_feasibility(
            {"inputI": -24.0, "inputTp": -12.0, "inputLra": 5.0}, self.PROFILE)
        self.assertTrue(verdict["feasible"])
        self.assertEqual(verdict["gainDb"], 10.0)
        self.assertEqual(verdict["estimatedTruePeak"], -2.0)
        self.assertEqual(verdict["exits"], [])

    def test_true_peak_ceiling_blocks_with_fix_numbers(self):
        verdict = loud_core.linear_feasibility(
            {"inputI": -30.0, "inputTp": -5.0, "inputLra": 4.0}, self.PROFILE)
        self.assertFalse(verdict["feasible"])
        self.assertEqual(verdict["blockedReasons"], ["true-peak"])
        self.assertEqual(verdict["ceilingLufs"], -26.5)
        joined = "|".join(verdict["exits"])
        self.assertIn("11.0", joined)   # 估算后 TP——提上限的数
        self.assertIn("-26.5", joined)  # 降目标的数
        self.assertIn("先压缩", joined)

    def test_lra_target_below_source_blocks(self):
        verdict = loud_core.linear_feasibility(
            {"inputI": -14.0, "inputTp": -20.0, "inputLra": 12.0}, self.PROFILE)
        self.assertFalse(verdict["feasible"])
        self.assertEqual(verdict["blockedReasons"], ["loudness-range"])

    def test_lowering_gain_never_tp_blocked(self):
        verdict = loud_core.linear_feasibility(
            {"inputI": -3.0, "inputTp": -1.0, "inputLra": 6.0}, self.PROFILE)
        self.assertTrue(verdict["feasible"])

    def test_chain_carries_all_measured_values(self):
        chain = loud_core.linear_chain(self.PROFILE, {"inputI": -24.0, "inputTp": -12.0,
                                                      "inputLra": 5.0, "inputThresh": -34.0})
        for token in ("measured_I=-24.0", "measured_TP=-12.0", "measured_LRA=5.0",
                      "measured_thresh=-34.0", "linear=true"):
            self.assertIn(token, chain)


class VersioningTests(unittest.TestCase):
    def test_next_versioned_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first, v1 = loud_core.next_versioned(directory, "响度-实测报告", ".json")
            first.write_text("a", encoding="utf-8")
            self.assertEqual(v1, "v0.1")
            second, v2 = loud_core.next_versioned(directory, "响度-实测报告", ".json")
            self.assertEqual(v2, "v0.2")
            self.assertEqual(first.read_text(encoding="utf-8"), "a")

    def test_profiles_match_contract(self):
        self.assertEqual(loud_core.PROFILES["video"],
                         {"integratedLufs": -14.0, "truePeakDbtp": -1.5, "lraTargetLu": 9.0})
        self.assertEqual(loud_core.PROFILES["podcast"]["integratedLufs"], -16.0)


class HeaderTests(unittest.TestCase):
    def test_artifact_header_identity(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            doc = loud_core.artifact_header("loud_plan", "p-1", Path(handle.name))
        self.assertEqual(doc["skill"], "loudness-expert")
        self.assertEqual(doc["purpose"], "loud_plan")
        self.assertEqual(doc["schemaVersion"], "0.1")

    def test_emit_prints_payload_and_exit_code(self):
        import contextlib
        import io
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(buf):
                loud_core.emit({"status": "blocked_x"}, 1)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("blocked_x", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
