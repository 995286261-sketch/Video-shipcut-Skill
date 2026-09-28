"""loud_plan 回归：目标显式化拒绝路径 + 端到端规划自洽（需 ffmpeg 的用例单独分组）。"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import loud_core      # noqa: E402
import loud_plan      # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def parse_args(**kwargs):
    base = dict(profile=None, target_lufs=None, true_peak=None, lra_target=None)
    base.update(kwargs)
    return argparse.Namespace(**base)


class TargetExplicitTests(unittest.TestCase):
    """⑧ 口径：不许半默认、不许两处口径混给。"""

    def test_no_target_given_refuses(self):
        with self.assertRaises(ValueError) as ctx:
            loud_plan.resolve_profile(parse_args())
        self.assertIn("显式", str(ctx.exception))

    def test_partial_triplet_refuses(self):
        with self.assertRaises(ValueError):
            loud_plan.resolve_profile(parse_args(target_lufs=-15.0, true_peak=-1.0))

    def test_profile_plus_explicit_refuses(self):
        with self.assertRaises(ValueError):
            loud_plan.resolve_profile(parse_args(profile="video", target_lufs=-15.0,
                                                 true_peak=-1.0, lra_target=9.0))

    def test_unknown_profile_refuses(self):
        with self.assertRaises(ValueError):
            loud_plan.resolve_profile(parse_args(profile="broadcast"))

    def test_explicit_triplet_accepted(self):
        profile = loud_plan.resolve_profile(parse_args(target_lufs=-15.0, true_peak=-1.0,
                                                       lra_target=8.0))
        self.assertEqual(profile["integratedLufs"], -15.0)

    def test_podcast_profile_values(self):
        profile = loud_plan.resolve_profile(parse_args(profile="podcast"))
        self.assertEqual(profile, {"integratedLufs": -16.0, "truePeakDbtp": -2.0,
                                   "lraTargetLu": 7.0})


def run_cli(argv):
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            loud_plan.main(argv)
    except SystemExit as exc:
        code = exc.code or 0
    return code, json.loads(buf.getvalue())


def make_sine(directory: Path, name: str, volume: float) -> Path:
    out = directory / name
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats",
                             "-f", "lavfi",
                             "-i", "sine=frequency=1000:sample_rate=48000:duration=2",
                             "-af", "volume={0}".format(volume), "-y", str(out)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return out


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg 缺席——端到端规划用例不适用（skip 非通过）")
class PlanE2ETests(unittest.TestCase):
    def test_ready_plan_carries_verbatim_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            src = make_sine(tmp_path, "a.wav", 0.5)
            code, doc = run_cli(["--input", str(src), "--output-dir", str(work),
                                 "--profile", "video", "--project-id", "loud-selftest"])
            self.assertEqual(doc["skill"], "loudness-expert")
            self.assertEqual(doc["purpose"], "loud_plan")
            self.assertEqual(doc["targetProfile"], loud_core.PROFILES["video"])
            self.assertIn("ceilingLufs", doc)
            self.assertEqual(Path(doc["output"]).name, "响度-归一化计划-v0.1.json")
            measured = doc["measured"]
            verdict = loud_core.linear_feasibility(measured, doc["targetProfile"])
            # 状态与自身算术必须自洽（规划不许言行不一）
            self.assertEqual(doc["status"] == "ready", verdict["feasible"])
            if doc["status"] == "ready":
                self.assertEqual(code, 0)
                self.assertIn("linear=true", doc["chain"])
                self.assertIn("measured_I={0}".format(measured["inputI"]), doc["chain"])
            else:
                self.assertEqual(code, 1)
                self.assertTrue(doc["exits"])

    def test_ready_plan_on_quiet_source_gain_is_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            src = make_sine(tmp_path, "q.wav", 0.02)
            _, doc = run_cli(["--input", str(src), "--output-dir", str(work),
                              "--profile", "video"])
            self.assertEqual(doc["status"], "ready")
            self.assertGreater(doc["gainDb"], 0)
            self.assertLess(doc["measured"]["estimatedTruePeak"]
                            if "estimatedTruePeak" in doc["measured"] else doc["estimatedTruePeak"],
                            doc["targetProfile"]["truePeakDbtp"] + 1e-6)

    def test_half_default_target_cli_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.wav"
            src.write_bytes(b"junk")
            code, doc = run_cli(["--input", str(src), "--output-dir", tmp,
                                 "--target-lufs", "-15.0"])
            self.assertEqual(code, 1)
            self.assertEqual(doc["status"], "error")
            self.assertIn("三件套", doc["error"])


if __name__ == "__main__":
    unittest.main()
